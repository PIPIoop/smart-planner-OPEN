from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import load_task_api_settings
from .models import (
    FinanceAccountRecord, FinanceCategoryRecord, FinanceDebtRecord, FinancePaymentRecord, FinancePaymentSettlementRequest, FinancePaymentSettlementResponse,
    FinancePeriodReport, FinanceSummaryResponse, FinanceTransactionRecord, FinancialGoalRecord,
    GoalCreationRequest, GoalCreationResponse, GoalRecord, HealthResponse, TaskCreateRequest,
    PlannerDataReplacementRequest, TaskGroupRecord, TaskRecord, TaskReplacementRequest,
)
from .repository import GoalNotFoundError, TaskConflictError, TaskNotFoundError, TaskRepository
from .finance_repository import FinanceConflictError, FinanceNotFoundError, FinanceValidationError
from .finance_service import FinanceService
from .security import derive_user_access_token
from .service import TaskService
from .subscriptions import (
    AccountOverrideRecord, AuditLogRecord, EntitlementSnapshot, OverrideCreateRequest,
    SubscriptionLimitError, SubscriptionRecord, SubscriptionUpdateRequest, TrialGrantRequest,
    UserNotificationRecord, ENTITLEMENT_FINANCE, LIMIT_AI_ACTIONS, LIMIT_FINANCE_ACCOUNTS,
    LIMIT_FINANCE_TRANSACTIONS, LIMIT_GOALS, LIMIT_GROUPS, LIMIT_VOICE_MESSAGES,
)
from .users import LEGACY_USER_ID, MultiTenantStore, PlannerUserRecord, UserAccessError, UserNotFoundError, UserRegistrationRequest, UserRegistrationResponse, UserRole, UserStatus

class WebSessionRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class WebSessionResponse(BaseModel):
    session_token: str
    admin_user_id: str
    expires_at: datetime


def create_app(
    repository: TaskRepository | None = None,
    *,
    multi_tenant_store: MultiTenantStore | None = None,
    service_token: str | None = None,
    web_admin_password: str | None = None,
) -> FastAPI:
    if repository is None and multi_tenant_store is None:
        settings = load_task_api_settings()
        multi_tenant_store = MultiTenantStore(settings.database_path)
        service_token = settings.service_token
        web_admin_password = settings.web_admin_password
    fixed_service = TaskService(repository) if repository is not None else None
    web_sessions: dict[str, tuple[str, datetime]] = {}

    def _extract_bearer(authorization: str | None) -> str | None:
        if authorization is None or not authorization.startswith("Bearer "):
            return None
        return authorization.removeprefix("Bearer ").strip()

    def require_service_token(
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        if service_token is None:
            return
        supplied = _extract_bearer(authorization)
        if supplied is None or not secrets.compare_digest(supplied, service_token):
            raise HTTPException(status_code=401, detail="Invalid service credential")

    def authenticated_user(
        authorization: Annotated[str | None, Header()] = None,
        x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    ) -> str:
        if service_token is None:
            return x_user_id or LEGACY_USER_ID
        if x_user_id is None:
            raise HTTPException(status_code=401, detail="X-User-Id is required")
        if authorization is not None and authorization.startswith("Session "):
            session_token = authorization.removeprefix("Session ").strip()
            session = web_sessions.get(session_token)
            now = datetime.now(timezone.utc)
            if session is None or session[1] <= now:
                web_sessions.pop(session_token, None)
                raise HTTPException(status_code=401, detail="Web session expired")
            if not secrets.compare_digest(session[0], x_user_id):
                raise HTTPException(status_code=401, detail="Invalid web session user")
            return x_user_id
        supplied = _extract_bearer(authorization)
        expected = derive_user_access_token(service_token, x_user_id)
        if supplied is None or not secrets.compare_digest(supplied, expected):
            raise HTTPException(status_code=401, detail="Invalid user credential")
        return x_user_id

    ServiceAuth = Depends(require_service_token)
    Principal = Annotated[str, Depends(authenticated_user)]

    def repository_for(principal_id: str, owner_id: str | None, *, write: bool = False) -> TaskRepository:
        selected_owner = owner_id or principal_id
        if multi_tenant_store is not None:
            try:
                if write:
                    multi_tenant_store.authorize_write(principal_id, selected_owner)
                else:
                    multi_tenant_store.authorize_calendar(principal_id, selected_owner)
                return multi_tenant_store.repository_for(selected_owner)
            except UserNotFoundError as error:
                raise HTTPException(status_code=404, detail="User not found") from error
            except UserAccessError as error:
                raise HTTPException(status_code=403, detail=str(error)) from error
        if repository is None:
            raise RuntimeError("Task repository is not configured")
        return repository

    def service_for(principal_id: str, owner_id: str | None, *, write: bool = False) -> TaskService:
        return TaskService(repository_for(principal_id, owner_id, write=write))

    def finance_for(principal_id: str, owner_id: str | None, *, write: bool = False) -> FinanceService:
        selected_owner = owner_id or principal_id
        if write and multi_tenant_store is not None:
            try:
                multi_tenant_store.authorize_write(principal_id, selected_owner)
            except UserNotFoundError as error:
                raise HTTPException(status_code=404, detail="User not found") from error
            except UserAccessError as error:
                raise HTTPException(status_code=403, detail=str(error)) from error
            is_admin = multi_tenant_store.is_admin(principal_id)
            if not multi_tenant_store.subscriptions.has_entitlement(
                selected_owner, ENTITLEMENT_FINANCE, admin=is_admin
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Full subscription is required to change finance data. Existing finance data remains available read-only.",
                )
        return FinanceService(repository_for(principal_id, owner_id, write=write))

    def _admin_required(principal_id: str) -> None:
        if multi_tenant_store is None:
            raise HTTPException(status_code=503, detail="User registry is unavailable")
        try:
            if not multi_tenant_store.is_admin(principal_id):
                raise UserAccessError("Administrator access required")
        except (UserNotFoundError, UserAccessError) as error:
            raise HTTPException(status_code=403, detail=str(error)) from error

    def _selected_owner(principal_id: str, owner_id: str | None) -> str:
        return owner_id or principal_id

    def _enforce_entity_limit(principal_id: str, owner_id: str | None, key: str, current_count: int) -> None:
        if multi_tenant_store is None:
            return
        owner = _selected_owner(principal_id, owner_id)
        try:
            multi_tenant_store.subscriptions.enforce_count_limit(
                owner, key, current_count, admin=multi_tenant_store.is_admin(principal_id)
            )
        except SubscriptionLimitError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error

    application = FastAPI(title="Smart Planner Task API", version="2.2.0")
    application.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept", "Authorization", "X-User-Id"],
    )

    @application.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", schema_version=2)

    @application.post("/api/v1/web/session", response_model=WebSessionResponse)
    def create_web_session(request: WebSessionRequest) -> WebSessionResponse:
        if web_admin_password is None or multi_tenant_store is None:
            raise HTTPException(status_code=503, detail="Web administrator login is unavailable")
        if not secrets.compare_digest(request.password, web_admin_password):
            raise HTTPException(status_code=401, detail="Invalid web administrator password")
        try:
            admin_user_id = multi_tenant_store.admin_user_id()
        except UserNotFoundError as error:
            raise HTTPException(status_code=503, detail="Administrator is not configured") from error
        expires_at = datetime.now(timezone.utc) + timedelta(hours=8)
        session_token = secrets.token_urlsafe(32)
        web_sessions[session_token] = (admin_user_id, expires_at)
        return WebSessionResponse(
            session_token=session_token,
            admin_user_id=admin_user_id,
            expires_at=expires_at,
        )

    @application.post("/api/v1/users/bootstrap-admin", response_model=PlannerUserRecord, dependencies=[ServiceAuth])
    def bootstrap_admin(request: UserRegistrationRequest) -> PlannerUserRecord:
        if multi_tenant_store is None:
            raise HTTPException(status_code=503, detail="User registry is unavailable")
        try:
            return multi_tenant_store.bootstrap_admin(request)
        except UserAccessError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error

    @application.post("/api/v1/users/requests", response_model=UserRegistrationResponse, status_code=201, dependencies=[ServiceAuth])
    def register_user(request: UserRegistrationRequest) -> UserRegistrationResponse:
        if multi_tenant_store is None:
            raise HTTPException(status_code=503, detail="User registry is unavailable")
        return multi_tenant_store.register(request)

    @application.get("/api/v1/users/me", response_model=PlannerUserRecord)
    def get_current_user(principal_id: str = Depends(authenticated_user)) -> PlannerUserRecord:
        if multi_tenant_store is None:
            raise HTTPException(status_code=503, detail="User registry is unavailable")
        try:
            return multi_tenant_store.touch(principal_id)
        except UserNotFoundError as error:
            raise HTTPException(status_code=404, detail="User not found") from error

    @application.get("/api/v1/users", response_model=list[PlannerUserRecord])
    def list_users(principal_id: str = Depends(authenticated_user)) -> list[PlannerUserRecord]:
        if multi_tenant_store is None:
            raise HTTPException(status_code=503, detail="User registry is unavailable")
        try:
            return multi_tenant_store.list_users(principal_id)
        except (UserNotFoundError, UserAccessError) as error:
            raise HTTPException(status_code=403, detail=str(error)) from error

    @application.post("/api/v1/users/{user_id}/status/{new_status}", response_model=PlannerUserRecord)
    def set_user_status(user_id: str, new_status: UserStatus, principal_id: str = Depends(authenticated_user)) -> PlannerUserRecord:
        if multi_tenant_store is None:
            raise HTTPException(status_code=503, detail="User registry is unavailable")
        try:
            return multi_tenant_store.set_status(principal_id, user_id, new_status)
        except UserNotFoundError as error:
            raise HTTPException(status_code=404, detail="User not found") from error
        except UserAccessError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error

    @application.delete("/api/v1/users/{user_id}", status_code=204)
    def delete_user(user_id: str, principal_id: str = Depends(authenticated_user)) -> Response:
        if multi_tenant_store is None:
            raise HTTPException(status_code=503, detail="User registry is unavailable")
        try:
            multi_tenant_store.delete_user(principal_id, user_id)
        except UserNotFoundError as error:
            raise HTTPException(status_code=404, detail="User not found") from error
        except UserAccessError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        return Response(status_code=204)

    @application.get("/api/v1/subscription/me", response_model=EntitlementSnapshot)
    def get_subscription_me(principal_id: str = Depends(authenticated_user)) -> EntitlementSnapshot:
        if multi_tenant_store is None:
            raise HTTPException(status_code=503, detail="Subscription registry is unavailable")
        try:
            return multi_tenant_store.entitlements_for(principal_id)
        except UserNotFoundError as error:
            raise HTTPException(status_code=404, detail="User not found") from error

    @application.post("/api/v1/subscription/usage/{usage_key}/consume", response_model=EntitlementSnapshot)
    def consume_subscription_usage(
        usage_key: str,
        amount: int = Query(default=1, ge=1, le=100),
        principal_id: str = Depends(authenticated_user),
    ) -> EntitlementSnapshot:
        if multi_tenant_store is None:
            raise HTTPException(status_code=503, detail="Subscription registry is unavailable")
        if usage_key not in {LIMIT_AI_ACTIONS, LIMIT_VOICE_MESSAGES, LIMIT_FINANCE_TRANSACTIONS}:
            raise HTTPException(status_code=400, detail="Unsupported usage key")
        try:
            multi_tenant_store.subscriptions.consume_usage(
                principal_id, usage_key, amount, admin=multi_tenant_store.is_admin(principal_id)
            )
            return multi_tenant_store.entitlements_for(principal_id)
        except SubscriptionLimitError as error:
            raise HTTPException(status_code=429, detail=str(error)) from error

    @application.get("/api/v1/users/me/notifications", response_model=list[UserNotificationRecord])
    def pending_notifications(principal_id: str = Depends(authenticated_user)) -> list[UserNotificationRecord]:
        if multi_tenant_store is None:
            return []
        return multi_tenant_store.subscriptions.pending_notifications(principal_id)

    @application.post("/api/v1/users/me/notifications/{notification_id}/delivered", status_code=204)
    def notification_delivered(notification_id: int, principal_id: str = Depends(authenticated_user)) -> Response:
        if multi_tenant_store is not None:
            multi_tenant_store.subscriptions.mark_notification_delivered(principal_id, notification_id)
        return Response(status_code=204)

    @application.get("/api/v1/admin/users/{user_id}/subscription", response_model=EntitlementSnapshot)
    def admin_get_subscription(user_id: str, principal_id: str = Depends(authenticated_user)) -> EntitlementSnapshot:
        _admin_required(principal_id)
        try:
            multi_tenant_store.get_user(user_id)  # type: ignore[union-attr]
            return multi_tenant_store.subscriptions.snapshot(user_id, admin=False)  # type: ignore[union-attr]
        except UserNotFoundError as error:
            raise HTTPException(status_code=404, detail="User not found") from error

    @application.put("/api/v1/admin/users/{user_id}/subscription", response_model=SubscriptionRecord)
    def admin_update_subscription(
        user_id: str, request: SubscriptionUpdateRequest, principal_id: str = Depends(authenticated_user)
    ) -> SubscriptionRecord:
        _admin_required(principal_id)
        try:
            target = multi_tenant_store.get_user(user_id)  # type: ignore[union-attr]
            if target.role is UserRole.admin:
                raise UserAccessError("Administrator subscription is managed by the server")
            return multi_tenant_store.subscriptions.update_subscription(principal_id, user_id, request)  # type: ignore[union-attr]
        except UserNotFoundError as error:
            raise HTTPException(status_code=404, detail="User not found") from error
        except UserAccessError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error

    @application.delete("/api/v1/admin/users/{user_id}/subscription", response_model=SubscriptionRecord)
    def admin_reset_subscription(user_id: str, principal_id: str = Depends(authenticated_user)) -> SubscriptionRecord:
        _admin_required(principal_id)
        target = multi_tenant_store.get_user(user_id)  # type: ignore[union-attr]
        if target.role is UserRole.admin:
            raise HTTPException(status_code=403, detail="Administrator subscription cannot be reset")
        return multi_tenant_store.subscriptions.reset_to_free(principal_id, user_id)  # type: ignore[union-attr]

    @application.post("/api/v1/admin/users/{user_id}/trial", response_model=SubscriptionRecord)
    def admin_grant_trial(
        user_id: str, request: TrialGrantRequest, principal_id: str = Depends(authenticated_user)
    ) -> SubscriptionRecord:
        _admin_required(principal_id)
        target = multi_tenant_store.get_user(user_id)  # type: ignore[union-attr]
        if target.role is UserRole.admin:
            raise HTTPException(status_code=403, detail="Administrator trial cannot be changed")
        return multi_tenant_store.subscriptions.grant_trial(principal_id, user_id, request.days)  # type: ignore[union-attr]

    @application.post("/api/v1/admin/users/{user_id}/overrides", response_model=AccountOverrideRecord, status_code=201)
    def admin_add_override(
        user_id: str, request: OverrideCreateRequest, principal_id: str = Depends(authenticated_user)
    ) -> AccountOverrideRecord:
        _admin_required(principal_id)
        multi_tenant_store.get_user(user_id)  # type: ignore[union-attr]
        try:
            return multi_tenant_store.subscriptions.add_override(principal_id, user_id, request)  # type: ignore[union-attr]
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.delete("/api/v1/admin/users/{user_id}/overrides/{override_id}", status_code=204)
    def admin_delete_override(
        user_id: str, override_id: str, principal_id: str = Depends(authenticated_user)
    ) -> Response:
        _admin_required(principal_id)
        try:
            multi_tenant_store.subscriptions.delete_override(principal_id, user_id, override_id)  # type: ignore[union-attr]
        except LookupError as error:
            raise HTTPException(status_code=404, detail="Override not found") from error
        return Response(status_code=204)

    @application.get("/api/v1/admin/users/{user_id}/audit", response_model=list[AuditLogRecord])
    def admin_subscription_audit(user_id: str, principal_id: str = Depends(authenticated_user)) -> list[AuditLogRecord]:
        _admin_required(principal_id)
        multi_tenant_store.get_user(user_id)  # type: ignore[union-attr]
        return multi_tenant_store.subscriptions.audit_log(user_id)  # type: ignore[union-attr]

    Owner = Annotated[str | None, Query(alias="userId")]

    @application.get("/api/v1/tasks", response_model=list[TaskRecord])
    def list_tasks(principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> list[TaskRecord]:
        return service_for(principal_id, user_id).list_tasks()

    @application.post("/api/v1/tasks", response_model=TaskRecord, status_code=201)
    def create_task(request: TaskCreateRequest, principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> TaskRecord:
        try:
            return service_for(principal_id, user_id, write=True).create_task(request)
        except TaskConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @application.put("/api/v1/tasks/{task_id}", response_model=TaskRecord)
    def update_task(task_id: str, task: TaskRecord, principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> TaskRecord:
        if task.id != task_id:
            raise HTTPException(status_code=400, detail="Path task ID does not match payload ID")
        try:
            return service_for(principal_id, user_id, write=True).update_task(task)
        except TaskNotFoundError as error:
            raise HTTPException(status_code=404, detail="Task not found") from error

    @application.delete("/api/v1/tasks/{task_id}", status_code=204)
    def delete_task(task_id: str, principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> Response:
        try:
            service_for(principal_id, user_id, write=True).delete_task(task_id)
        except TaskNotFoundError as error:
            raise HTTPException(status_code=404, detail="Task not found") from error
        return Response(status_code=204)

    @application.get("/api/v1/groups", response_model=list[TaskGroupRecord])
    def list_groups(principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> list[TaskGroupRecord]:
        return service_for(principal_id, user_id).list_groups()

    @application.post("/api/v1/groups", response_model=TaskGroupRecord, status_code=201)
    def create_group(group: TaskGroupRecord, principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> TaskGroupRecord:
        current = service_for(principal_id, user_id).list_groups()
        _enforce_entity_limit(principal_id, user_id, LIMIT_GROUPS, len(current))
        try:
            return service_for(principal_id, user_id, write=True).create_group(group)
        except TaskConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @application.put("/api/v1/groups/{group_id}", response_model=TaskGroupRecord)
    def update_group(group_id: str, group: TaskGroupRecord, principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> TaskGroupRecord:
        if group.id != group_id:
            raise HTTPException(status_code=400, detail="Path group ID does not match payload ID")
        try:
            return service_for(principal_id, user_id, write=True).update_group(group)
        except GoalNotFoundError as error:
            raise HTTPException(status_code=404, detail="Group not found") from error

    @application.delete("/api/v1/groups/{group_id}", status_code=204)
    def delete_group(group_id: str, principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> Response:
        try:
            service_for(principal_id, user_id, write=True).delete_group(group_id)
        except GoalNotFoundError as error:
            raise HTTPException(status_code=404, detail="Group not found") from error
        return Response(status_code=204)

    @application.get("/api/v1/goals", response_model=list[GoalRecord])
    def list_goals(principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> list[GoalRecord]:
        return service_for(principal_id, user_id).list_goals()

    @application.post("/api/v1/goals", response_model=GoalCreationResponse, status_code=201)
    def create_goal(request: GoalCreationRequest, principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> GoalCreationRequest:
        current = service_for(principal_id, user_id).list_goals()
        _enforce_entity_limit(principal_id, user_id, LIMIT_GOALS, len(current))
        try:
            return service_for(principal_id, user_id, write=True).create_goal(request)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except TaskConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @application.delete("/api/v1/goals/{goal_id}", status_code=204)
    def delete_goal(goal_id: str, principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> Response:
        try:
            service_for(principal_id, user_id, write=True).delete_goal(goal_id)
        except GoalNotFoundError as error:
            raise HTTPException(status_code=404, detail="Goal not found") from error
        return Response(status_code=204)

    @application.put("/api/v1/planner-data", status_code=204)
    def replace_planner_data(
        request: PlannerDataReplacementRequest,
        principal_id: str = Depends(authenticated_user),
        user_id: str | None = Query(default=None, alias="userId"),
    ) -> Response:
        service = service_for(principal_id, user_id, write=True)
        if multi_tenant_store is not None:
            owner = _selected_owner(principal_id, user_id)
            try:
                limits = multi_tenant_store.subscriptions.snapshot(
                    owner, admin=multi_tenant_store.is_admin(principal_id)
                ).limits
                group_limit = limits[LIMIT_GROUPS]
                goal_limit = limits[LIMIT_GOALS]
                if group_limit >= 0 and len(request.groups) > group_limit:
                    raise SubscriptionLimitError(LIMIT_GROUPS, group_limit)
                if goal_limit >= 0 and len(request.goals) > goal_limit:
                    raise SubscriptionLimitError(LIMIT_GOALS, goal_limit)
            except SubscriptionLimitError as error:
                raise HTTPException(status_code=403, detail=str(error)) from error
        try:
            service.replace_planner_data(
                request.tasks, request.goals, request.groups
            )
        except TaskConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return Response(status_code=204)

    @application.put("/api/v1/tasks", status_code=204)
    def replace_tasks(request: TaskReplacementRequest, principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> Response:
        try:
            service_for(principal_id, user_id, write=True).replace_all(request.tasks)
        except TaskConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return Response(status_code=204)

    @application.get("/api/v1/finance/summary", response_model=FinanceSummaryResponse)
    def finance_summary(principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> FinanceSummaryResponse:
        return finance_for(principal_id, user_id).summary()

    @application.get("/api/v1/finance/report", response_model=FinancePeriodReport)
    def finance_period_report(
        period: str = Query(default="month", pattern="^(day|week|month|year)$"),
        principal_id: str = Depends(authenticated_user),
        user_id: str | None = Query(default=None, alias="userId"),
    ) -> FinancePeriodReport:
        return finance_for(principal_id, user_id).period_report(period)

    @application.get("/api/v1/finance/accounts", response_model=list[FinanceAccountRecord])
    def list_finance_accounts(principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> list[FinanceAccountRecord]:
        return finance_for(principal_id, user_id).list_accounts()

    @application.post("/api/v1/finance/accounts", response_model=FinanceAccountRecord, status_code=201)
    def create_finance_account(account: FinanceAccountRecord, principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> FinanceAccountRecord:
        if multi_tenant_store is not None:
            current = finance_for(principal_id, user_id).list_accounts()
            _enforce_entity_limit(principal_id, user_id, LIMIT_FINANCE_ACCOUNTS, len(current))
        try:
            return finance_for(principal_id, user_id, write=True).create_account(account)
        except FinanceConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @application.put("/api/v1/finance/accounts/{account_id}", response_model=FinanceAccountRecord)
    def update_finance_account(account_id: str, account: FinanceAccountRecord, principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> FinanceAccountRecord:
        if account.id != account_id:
            raise HTTPException(status_code=400, detail="Path account ID does not match payload ID")
        try:
            return finance_for(principal_id, user_id, write=True).update_account(account)
        except FinanceNotFoundError as error:
            raise HTTPException(status_code=404, detail="Account not found") from error

    @application.delete("/api/v1/finance/accounts/{account_id}", status_code=204)
    def delete_finance_account(account_id: str, principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> Response:
        try:
            finance_for(principal_id, user_id, write=True).delete_account(account_id)
        except FinanceNotFoundError as error:
            raise HTTPException(status_code=404, detail="Account not found") from error
        except FinanceValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return Response(status_code=204)

    @application.get("/api/v1/finance/categories", response_model=list[FinanceCategoryRecord])
    def list_finance_categories(principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> list[FinanceCategoryRecord]:
        return finance_for(principal_id, user_id).list_categories()

    @application.post("/api/v1/finance/categories", response_model=FinanceCategoryRecord, status_code=201)
    def create_finance_category(category: FinanceCategoryRecord, principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> FinanceCategoryRecord:
        try:
            return finance_for(principal_id, user_id, write=True).create_category(category)
        except FinanceConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @application.get("/api/v1/finance/transactions", response_model=list[FinanceTransactionRecord])
    def list_finance_transactions(limit: int = Query(default=200, ge=1, le=1000), principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> list[FinanceTransactionRecord]:
        return finance_for(principal_id, user_id).list_transactions(limit)

    @application.post("/api/v1/finance/transactions", response_model=FinanceTransactionRecord, status_code=201)
    def create_finance_transaction(transaction: FinanceTransactionRecord, principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> FinanceTransactionRecord:
        owner = _selected_owner(principal_id, user_id)
        service = finance_for(principal_id, user_id, write=True)
        reserved = False
        if multi_tenant_store is not None:
            try:
                multi_tenant_store.subscriptions.consume_usage(
                    owner,
                    LIMIT_FINANCE_TRANSACTIONS,
                    admin=multi_tenant_store.is_admin(principal_id),
                )
                reserved = True
            except SubscriptionLimitError as error:
                raise HTTPException(status_code=429, detail=str(error)) from error
        try:
            return service.create_transaction(transaction)
        except FinanceConflictError as error:
            if reserved:
                multi_tenant_store.subscriptions.refund_usage(owner, LIMIT_FINANCE_TRANSACTIONS)  # type: ignore[union-attr]
            raise HTTPException(status_code=409, detail=str(error)) from error
        except FinanceValidationError as error:
            if reserved:
                multi_tenant_store.subscriptions.refund_usage(owner, LIMIT_FINANCE_TRANSACTIONS)  # type: ignore[union-attr]
            raise HTTPException(status_code=422, detail=str(error)) from error
        except Exception:
            if reserved:
                multi_tenant_store.subscriptions.refund_usage(owner, LIMIT_FINANCE_TRANSACTIONS)  # type: ignore[union-attr]
            raise

    @application.delete("/api/v1/finance/transactions/{transaction_id}", status_code=204)
    def delete_finance_transaction(transaction_id: str, principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> Response:
        try:
            finance_for(principal_id, user_id, write=True).delete_transaction(transaction_id)
        except FinanceNotFoundError as error:
            raise HTTPException(status_code=404, detail="Transaction not found") from error
        return Response(status_code=204)

    @application.get("/api/v1/finance/goals", response_model=list[FinancialGoalRecord])
    def list_financial_goals(principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> list[FinancialGoalRecord]:
        return finance_for(principal_id, user_id).list_goals()

    @application.post("/api/v1/finance/goals", response_model=FinancialGoalRecord, status_code=201)
    def create_financial_goal(goal: FinancialGoalRecord, principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> FinancialGoalRecord:
        try:
            return finance_for(principal_id, user_id, write=True).create_goal(goal)
        except (FinanceConflictError, FinanceValidationError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.put("/api/v1/finance/goals/{goal_id}", response_model=FinancialGoalRecord)
    def update_financial_goal(goal_id: str, goal: FinancialGoalRecord, principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> FinancialGoalRecord:
        if goal.id != goal_id:
            raise HTTPException(status_code=400, detail="Path goal ID does not match payload ID")
        try:
            return finance_for(principal_id, user_id, write=True).update_goal(goal)
        except FinanceNotFoundError as error:
            raise HTTPException(status_code=404, detail="Financial goal not found") from error
        except FinanceValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.delete("/api/v1/finance/goals/{goal_id}", status_code=204)
    def delete_financial_goal(goal_id: str, principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> Response:
        try:
            finance_for(principal_id, user_id, write=True).delete_goal(goal_id)
        except FinanceNotFoundError as error:
            raise HTTPException(status_code=404, detail="Financial goal not found") from error
        return Response(status_code=204)

    @application.get("/api/v1/finance/payments", response_model=list[FinancePaymentRecord])
    def list_finance_payments(principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> list[FinancePaymentRecord]:
        return finance_for(principal_id, user_id).list_payments()

    @application.post("/api/v1/finance/payments", response_model=FinancePaymentRecord, status_code=201)
    def create_finance_payment(payment: FinancePaymentRecord, principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> FinancePaymentRecord:
        try:
            return finance_for(principal_id, user_id, write=True).create_payment(payment)
        except (FinanceConflictError, FinanceValidationError, TaskConflictError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.put("/api/v1/finance/payments/{payment_id}", response_model=FinancePaymentRecord)
    def update_finance_payment(payment_id: str, payment: FinancePaymentRecord, principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> FinancePaymentRecord:
        if payment.id != payment_id:
            raise HTTPException(status_code=400, detail="Path payment ID does not match payload ID")
        try:
            return finance_for(principal_id, user_id, write=True).update_payment(payment)
        except FinanceNotFoundError as error:
            raise HTTPException(status_code=404, detail="Payment not found") from error
        except (FinanceValidationError, TaskConflictError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.post(
        "/api/v1/finance/payments/{payment_id}/settle",
        response_model=FinancePaymentSettlementResponse,
    )
    def settle_finance_payment(
        payment_id: str,
        request: FinancePaymentSettlementRequest,
        principal_id: str = Depends(authenticated_user),
        user_id: str | None = Query(default=None, alias="userId"),
    ) -> FinancePaymentSettlementResponse:
        owner = _selected_owner(principal_id, user_id)
        service = finance_for(principal_id, user_id, write=True)
        already_settled = service.payment_settlement_exists(
            payment_id, request.expected_due_date
        )
        reserved = False
        if multi_tenant_store is not None and not already_settled:
            try:
                multi_tenant_store.subscriptions.consume_usage(
                    owner,
                    LIMIT_FINANCE_TRANSACTIONS,
                    admin=multi_tenant_store.is_admin(principal_id),
                )
                reserved = True
            except SubscriptionLimitError as error:
                raise HTTPException(status_code=429, detail=str(error)) from error
        try:
            result = service.settle_payment(
                payment_id, request.expected_due_date, request.paid_at
            )
            if reserved and not result.created:
                multi_tenant_store.subscriptions.refund_usage(owner, LIMIT_FINANCE_TRANSACTIONS)  # type: ignore[union-attr]
            return result
        except FinanceNotFoundError as error:
            if reserved:
                multi_tenant_store.subscriptions.refund_usage(owner, LIMIT_FINANCE_TRANSACTIONS)  # type: ignore[union-attr]
            raise HTTPException(status_code=404, detail="Payment not found") from error
        except (FinanceConflictError, FinanceValidationError, TaskConflictError) as error:
            if reserved:
                multi_tenant_store.subscriptions.refund_usage(owner, LIMIT_FINANCE_TRANSACTIONS)  # type: ignore[union-attr]
            raise HTTPException(status_code=422, detail=str(error)) from error
        except Exception:
            if reserved:
                multi_tenant_store.subscriptions.refund_usage(owner, LIMIT_FINANCE_TRANSACTIONS)  # type: ignore[union-attr]
            raise

    @application.delete("/api/v1/finance/payments/{payment_id}", status_code=204)
    def delete_finance_payment(payment_id: str, principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> Response:
        try:
            finance_for(principal_id, user_id, write=True).delete_payment(payment_id)
        except FinanceNotFoundError as error:
            raise HTTPException(status_code=404, detail="Payment not found") from error
        return Response(status_code=204)

    @application.get("/api/v1/finance/debts", response_model=list[FinanceDebtRecord])
    def list_finance_debts(principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> list[FinanceDebtRecord]:
        return finance_for(principal_id, user_id).list_debts()

    @application.post("/api/v1/finance/debts", response_model=FinanceDebtRecord, status_code=201)
    def create_finance_debt(debt: FinanceDebtRecord, principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> FinanceDebtRecord:
        try:
            return finance_for(principal_id, user_id, write=True).create_debt(debt)
        except FinanceConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @application.put("/api/v1/finance/debts/{debt_id}", response_model=FinanceDebtRecord)
    def update_finance_debt(debt_id: str, debt: FinanceDebtRecord, principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> FinanceDebtRecord:
        if debt.id != debt_id:
            raise HTTPException(status_code=400, detail="Path debt ID does not match payload ID")
        try:
            return finance_for(principal_id, user_id, write=True).update_debt(debt)
        except FinanceNotFoundError as error:
            raise HTTPException(status_code=404, detail="Debt not found") from error

    @application.delete("/api/v1/finance/debts/{debt_id}", status_code=204)
    def delete_finance_debt(debt_id: str, principal_id: str = Depends(authenticated_user), user_id: str | None = Query(default=None, alias="userId")) -> Response:
        try:
            finance_for(principal_id, user_id, write=True).delete_debt(debt_id)
        except FinanceNotFoundError as error:
            raise HTTPException(status_code=404, detail="Debt not found") from error
        return Response(status_code=204)

    return application


def create_default_app() -> FastAPI:
    return create_app()
