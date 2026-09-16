[app]

title = Nexus
package.name = nexus
package.domain = com.nexus.app

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json

version = 1.0.0
requirements = python3,kivy==2.3.0,kivymd==1.2.0,pillow,requests,urllib3,certifi,chardet,idna

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE,VIBRATE,WAKE_LOCK

android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True
android.debug = True

[buildozer]
log_level = 2
warn_on_root = 0
