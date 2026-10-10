$ErrorActionPreference = "Stop"
flutter pub get
flutter analyze
flutter test
flutter build web --release
Write-Host "Готово: build/web"
