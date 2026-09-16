#
============================================================
# NEXUS v3 - Main User App
# Firebase Auth + Firestore + Chat + Settings + Notifications
# ============================================================

import os
import re
import json
import sqlite3
import requests
from datetime import datetime, timedelta

from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.screenmanager import MDScreenManager
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.card import MDCard
from kivymd.uix.button import MDFlatButton, MDRaisedButton, MDIconButton
from kivymd.uix.textfield import MDTextField
from kivymd.uix.bottomnavigation import MDBottomNavigation, MDBottomNavigationItem
from kivy.lang import Builder
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.clock import Clock
from kivy.utils import platform

Window.clearcolor = (0.06, 0.06, 0.1, 1)


# ============================================================
# CONFIG
# ============================================================
FIREBASE_API_KEY = "AIzaSyAJDEalq7on3_gL7PF6JTIPKI71anS-iqY"
FIREBASE_PROJECT_ID = "nexus-78881"

BAD_WORDS = ["spam", "scam", "badword1", "badword2", "বাজে"]

SESSION_DAYS = 7


# ============================================================
# NAME VALIDATOR
# ============================================================
class NameValidator:
    @staticmethod
    def is_valid(name):
        if not name:
            return False, "Name khali rakha jabe na"
        name = name.strip()
        if len(name) < 2:
            return False, "Name kompokkhe 2 okkhor"
        if len(name) > 30:
            return False, "Name shorboccho 30 okkhor"
        pattern = r'^[a-zA-Z\u0980-\u09FF\s]+$'
        if not re.match(pattern, name):
            return False, "Shudhu okkhor & space (number/emoji noy)"
        return True, "OK"


# ============================================================
# CONTENT GUARD
# ============================================================
class ContentGuard:
    @staticmethod
    def check(text):
        issues = []
        tl = text.lower()
        for w in BAD_WORDS:
            if w in tl:
                issues.append(f"Bad: {w}")
        if text.count("!") > 5:
            issues.append("Too many !")
        if "bit.ly" in tl or "tinyurl" in tl:
            issues.append("Suspicious link")
        return len(issues) == 0, issues


# ============================================================
# NOTIFICATION MANAGER
# ============================================================
class NotificationManager:
    def __init__(self):
        self.notifications = []

    def add(self, title, message, ntype="info"):
        notif = {
            "id": len(self.notifications) + 1,
            "title": title,
            "message": message,
            "type": ntype,
            "time": datetime.now().strftime("%H:%M"),
            "read": False,
        }
        self.notifications.insert(0, notif)
        self.play_sound()
        self.vibrate()
        return notif

    def play_sound(self):
        try:
            if platform == "android":
                from jnius import autoclass
                RingtoneManager = autoclass('android.media.RingtoneManager')
                MediaPlayer = autoclass('android.media.MediaPlayer')
                Context = autoclass('org.kivy.android.PythonActivity').mActivity
                notif_uri = RingtoneManager.getDefaultUri(
                    RingtoneManager.TYPE_NOTIFICATION)
                player = MediaPlayer()
                player.setDataSource(Context, notif_uri)
                player.prepare()
                player.start()
                print("Sound played")
            else:
                print("[Sound] Notification")
        except Exception as e:
            print(f"Sound skipped: {e}")

    def vibrate(self):
        try:
            if platform == "android":
                from jnius import autoclass
                Context = autoclass('org.kivy.android.PythonActivity').mActivity
                Vibrator = autoclass('android.os.Vibrator')
                vibrator = Context.getSystemService(Context.VIBRATOR_SERVICE)
                if vibrator:
                    vibrator.vibrate(300)
                    print("Vibrated")
        except Exception as e:
            print(f"Vibrate skipped: {e}")

    def get_all(self):
        return self.notifications

    def mark_all_read(self):
        for n in self.notifications:
            n["read"] = True

    def unread_count(self):
        return sum(1 for n in self.notifications if not n["read"])


#============================================================
# FIREBASE AUTH
# ============================================================
class FirebaseAuth:
    BASE_URL = "https://identitytoolkit.googleapis.com/v1"

    def __init__(self, api_key):
        self.api_key = api_key
        self.session_file = os.path.join(os.getcwd(), "nexus_session.json")
        self.current_user = None

    def signup(self, email, password):
        try:
            url = f"{self.BASE_URL}/accounts:signUp?key={self.api_key}"
            r = requests.post(url, json={
                "email": email, "password": password, "returnSecureToken": True
            }, timeout=15)
            res = r.json()
            if r.status_code == 200:
                return True, "Account created!", res
            error = res.get("error", {}).get("message", "Unknown")
            return False, self.friendly_error(error), None
        except requests.exceptions.ConnectionError:
            return False, "Internet nei", None
        except Exception as e:
            return False, f"Error: {e}", None

    def login(self, email, password):
        try:
            url = f"{self.BASE_URL}/accounts:signInWithPassword?key={self.api_key}"
            r = requests.post(url, json={
                "email": email, "password": password, "returnSecureToken": True
            }, timeout=15)
            res = r.json()
            if r.status_code == 200:
                user = {
                    "email": res["email"],
                    "localId": res["localId"],
                    "idToken": res["idToken"],
                    "login_at": datetime.now().isoformat(),
                }
                self.current_user = user
                return True, "Login OK!", user
            error = res.get("error", {}).get("message", "Unknown")
            return False, self.friendly_error(error), None
        except requests.exceptions.ConnectionError:
            return False, "Internet nei", None
        except Exception as e:
            return False, f"Error: {e}", None

    def save_session(self, user):
        try:
            with open(self.session_file, "w") as f:
                json.dump(user, f)
            return True
        except:
            return False

    def load_session(self):
        try:
            if not os.path.exists(self.session_file):
                return None
            with open(self.session_file, "r") as f:
                user = json.load(f)
            if "login_at" in user:
                login_time = datetime.fromisoformat(user["login_at"])
                if datetime.now() - login_time > timedelta(days=SESSION_DAYS):
                    print("Session expired")
                    self.clear_session()
                    return None
            self.current_user = user
            return user
        except:
            return None

    def clear_session(self):
        try:
            if os.path.exists(self.session_file):
                os.remove(self.session_file)
            self.current_user = None
        except:
            pass

    def friendly_error(self, code):
        errors = {
            "EMAIL_EXISTS": "Ei Email agei register kora ache",
            "EMAIL_NOT_FOUND": "Ei Email diye account nei",
            "INVALID_PASSWORD": "Password bhul",
            "INVALID_EMAIL": "Sothik Email din",
            "WEAK_PASSWORD": "Password kompokkhe 8 okkhor",
            "INVALID_LOGIN_CREDENTIALS": "Email ba Password bhul",
        }
        for k, m in errors.items():
            if k in code:
                return m
        return f"{code}"


# ============================================================
# FIRESTORE
# ============================================================
class FirestoreDB:
    def __init__(self, project_id, id_token=None):
        self.project_id = project_id
        self.base_url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents"
        self.id_token = id_token

    def set_token(self, token):
        self.id_token = token

    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self.id_token:
            h["Authorization"] = f"Bearer {self.id_token}"
        return h

    def _to_fs(self, data):
        result = {}
        for k, v in data.items():
            if isinstance(v, str):
                result[k] = {"stringValue": v}
            elif isinstance(v, bool):
                result[k] = {"booleanValue": v}
            elif isinstance(v, int):
                result[k] = {"integerValue": str(v)}
            else:
                result[k] = {"stringValue": str(v)}
        return {"fields": result}

    def _from_fs(self, doc):
        if "fields" not in doc:
            return {}
        r = {}
        for k, v in doc["fields"].items():
            if "stringValue" in v:
                r[k] = v["stringValue"]
            elif "integerValue" in v:
                r[k] = int(v["integerValue"])
            elif "booleanValue" in v:
                r[k] = v["booleanValue"]
        if "name" in doc:
            r["_id"] = doc["name"].split("/")[-1]
        return r

    def save_user_profile(self, uid, data):
        try:
            url = f"{self.base_url}/users/{uid}"
            r = requests.patch(url, json=self._to_fs(data),
                             headers=self._headers(), timeout=15)
            return r.status_code in (200, 201), r.json()
        except Exception as e:
            return False, str(e)

    def get_user_profile(self, uid):
        try:
            url = f"{self.base_url}/users/{uid}"
            r = requests.get(url, headers=self._headers(), timeout=15)
            if r.status_code == 200:
                return True, self._from_fs(r.json())
            return False, None
        except:
            return False, None

    def add_post(self, data):
        try:
            url = f"{self.base_url}/posts"
            r = requests.post(url, json=self._to_fs(data),
                            headers=self._headers(), timeout=15)
            if r.status_code in (200, 201):
                return True, self._from_fs(r.json())
            return False, r.json()
        except Exception as e:
            return False, str(e)

    def get_posts(self):
        try:
            url = f"{self.base_url}/posts"
            r = requests.get(url, headers=self._headers(), timeout=15)
            if r.status_code == 200:
                docs = r.json().get("documents", [])
                return True, [self._from_fs(d) for d in docs]
            return False, []
        except:
            return False, []

    def is_banned(self, uid):
        try:
            url = f"{self.base_url}/banned/{uid}"
            r = requests.get(url, headers=self._headers(), timeout=10)
            return r.status_code == 200
        except:
            return False


# ============================================================
# MESSAGE BUBBLE
# ============================================================
class MessageBubble(MDCard):
    def __init__(self, text, is_me=False, time="", **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.radius = [dp(15)]
        self.padding = dp(10)
        lines = max(1, len(text) // 30 + 1)
        height = dp(35 + lines * 20)
        if is_me:
            self.md_bg_color = (0.42, 0.36, 0.91, 1)
            self.pos_hint = {"right": 0.98}
        else:
            self.md_bg_color = (0.18, 0.18, 0.25, 1)
            self.pos_hint = {"left": 0.02}
        self.size = (dp(240), height)
        col = MDBoxLayout(orientation="vertical", spacing=dp(2))
        col.add_widget(MDLabel(
            text=text, theme_text_color="Custom",
            text_color=(1, 1, 1, 1),
            size_hint_y=None, height=dp(height - 15),
            text_size=(dp(220), None),
        ))
        if time:
            col.add_widget(MDLabel(
                text=time, theme_text_color="Custom",
                text_color=(0.8, 0.8, 0.8, 1),
                font_style="Caption", halign="right",
                size_hint_y=None, height=dp(15),
            ))
        self.add_widget(col)


# ============================================================
# SQLITE DB
# ============================================================
class LocalDB:
    def __init__(self, db_name="nexus_v3.db"):
        self.db_path = os.path.join(os.getcwd(), db_name)
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                last_msg TEXT,
                last_time TEXT,
                unread INTEGER DEFAULT 0
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_with TEXT,
                text TEXT,
                is_me INTEGER,
                created_at TEXT
            )
        """)
        self.conn.commit()

    def ensure_chat(self, name):
        self.cursor.execute("SELECT name FROM chats WHERE name=?", (name,))
        if not self.cursor.fetchone():
            self.cursor.execute(
                "INSERT INTO chats (name, last_msg, last_time) VALUES (?, '', '')",
                (name,))
            self.conn.commit()

    def get_chats(self):
        self.cursor.execute(
            "SELECT name, last_msg, last_time, unread FROM chats ORDER BY id DESC")
        return self.cursor.fetchall()

    def update_chat(self, name, msg, time, inc=False):
        if inc:
            self.cursor.execute(
                "UPDATE chats SET last_msg=?, last_time=?, unread=unread+1 WHERE name=?",
                (msg, time, name))
        else:
            self.cursor.execute(
                "UPDATE chats SET last_msg=?, last_time=? WHERE name=?",
                (msg, time, name))
        self.conn.commit()

    def reset_unread(self, name):
        self.cursor.execute("UPDATE chats SET unread=0 WHERE name=?", (name,))
        self.conn.commit()

    def add_message(self, chat_with, text, is_me):
        self.cursor.execute("""
            INSERT INTO messages (chat_with, text, is_me, created_at)
            VALUES (?, ?, ?, ?)
        """, (chat_with, text, 1 if is_me else 0,
              datetime.now().strftime("%H:%M")))
        self.conn.commit()

    def get_messages(self, chat_with):
        self.cursor.execute(
            "SELECT text, is_me, created_at FROM messages WHERE chat_with=? ORDER BY id ASC",
            (chat_with,))
        return self.cursor.fetchall()

    def close(self):
        self.conn.close()


# ============================================================
# UI (KV)
# ============================================================
KV = '''
MDScreenManager:
    id: sm

    MDScreen:
        name: "login"
        md_bg_color: 0.06, 0.06, 0.1, 1
        MDBoxLayout:
            orientation: "vertical"
            padding: "20dp"
            Widget:
            MDLabel:
                text: "NEXUS"
                halign: "center"
                theme_text_color: "Custom"
                text_color: 0.42, 0.36, 0.91, 1
                font_style: "H2"
                bold: True
                size_hint_y: None
                height: "70dp"
            MDLabel:
                text: "Connect Everything"
                halign: "center"
                theme_text_color: "Custom"
                text_color: 0.63, 0.63, 0.69, 1
                size_hint_y: None
                height: "25dp"
            Widget:
                size_hint_y: None
                height: "30dp"
            MDTextField:
                id: login_email
                hint_text: "Email"
                mode: "rectangle"
                icon_right: "email"
                size_hint_x: None
                width: "300dp"
                pos_hint: {"center_x": 0.5}
            Widget:
                size_hint_y: None
                height: "10dp"
            MDTextField:
                id: login_password
                hint_text: "Password"
                mode: "rectangle"
                password: True
                icon_right: "eye-off"
                size_hint_x: None
                width: "300dp"
                pos_hint: {"center_x": 0.5}
            Widget:
                size_hint_y: None
                height: "15dp"
            MDLabel:
                id: login_status
                text: ""
                halign: "center"
                theme_text_color: "Custom"
                text_color: 1, 0.4, 0.4, 1
                size_hint_y: None
                height: "30dp"
            MDRaisedButton:
                text: "LOGIN"
                size_hint_x: None
                width: "300dp"
                height: "50dp"
                pos_hint: {"center_x": 0.5}
                md_bg_color: 0.42, 0.36, 0.91, 1
                on_release: app.do_login()
            Widget:
                size_hint_y: None
                height: "15dp"
            MDBoxLayout:
                size_hint_y: None
                height: "40dp"
                pos_hint: {"center_x": 0.5}
                size_hint_x: None
                width: "300dp"
                MDLabel:
                    text: "New here?"
                    halign: "right"
                    theme_text_color: "Custom"
                    text_color: 0.63, 0.63, 0.69, 1
                MDFlatButton:
                    text: "Sign Up"
                    theme_text_color: "Custom"
                    text_color: 0.0, 0.81, 0.79, 1
                    on_release: app.go_screen("signup")
            Widget:

    MDScreen:
        name: "signup"
        md_bg_color: 0.06, 0.06, 0.1, 1
        MDBoxLayout:
            orientation: "vertical"
            padding: "20dp"
            Widget:
                size_hint_y: None
                height: "15dp"
            MDLabel:
                text: "Create Account"
                halign: "center"
                theme_text_color: "Custom"
                text_color: 1,1,1,1
                font_style: "H4"
                bold: True
                size_hint_y: None
                height: "50dp"
            Widget:
                size_hint_y: None
                height: "15dp"
            MDTextField:
                id: su_name
                hint_text: "Full Name (only letters)"
                mode: "rectangle"
                icon_right: "account"
                size_hint_x: None
                width: "300dp"
                pos_hint: {"center_x": 0.5}
            Widget:
                size_hint_y: None
                height: "8dp"
            MDTextField:
                id: su_email
                hint_text: "Email"
                mode: "rectangle"
                icon_right: "email"
                size_hint_x: None
                width: "300dp"
                pos_hint: {"center_x": 0.5}
            Widget:
                size_hint_y: None
                height: "8dp"
            MDTextField:
                id: su_password
                hint_text: "Password (min 8, letter+number)"
                mode: "rectangle"
                password: True
                icon_right: "eye-off"
                size_hint_x: None
                width: "300dp"
                pos_hint: {"center_x": 0.5}
            Widget:
                size_hint_y: None
                height: "8dp"
            MDTextField:
                id: su_confirm
                hint_text: "Confirm Password"
                mode: "rectangle"
                password: True
                icon_right: "eye-off"
                size_hint_x: None
                width: "300dp"
                pos_hint: {"center_x": 0.5}
            Widget:
                size_hint_y: None
                height: "10dp"
            MDLabel:
                id: su_status
                text: ""
                halign: "center"
                theme_text_color: "Custom"
                text_color: 1, 0.4, 0.4, 1
                size_hint_y: None
                height: "40dp"
            MDRaisedButton:
                text: "SIGN UP"
                size_hint_x: None
                width: "300dp"
                height: "50dp"
                pos_hint: {"center_x": 0.5}
                md_bg_color: 0.42, 0.36, 0.91, 1
                on_release: app.do_signup()
            Widget:
                size_hint_y: None
                height: "10dp"
            MDFlatButton:
                text: "Back to Login"
                size_hint_x: None
                width: "200dp"
                pos_hint: {"center_x": 0.5}
                theme_text_color: "Custom"
                text_color: 0.0, 0.81, 0.79, 1
                on_release: app.go_screen("login")
            Widget:

    MDScreen:
        name: "home"
        md_bg_color: 0.06, 0.06, 0.1, 1
        MDBottomNavigation:
            id: bottom_nav
            panel_color: 0.12, 0.12, 0.18, 1
            text_color_active: 0.42, 0.36, 0.91, 1

            MDBottomNavigationItem:
                name: "tab_home"
                text: "Home"
                icon: "home"
                MDBoxLayout:
                    orientation: "vertical"
                    MDTopAppBar:
                        title: "NEXUS"
                        md_bg_color: 0.12, 0.12, 0.18, 1
                        specific_text_color: 0.42, 0.36, 0.91, 1
                        right_action_items: [["bell-outline", lambda x: app.open_notifications()], ["refresh", lambda x: app.load_posts()]]
                    ScrollView:
                        MDBoxLayout:
                            id: feed
                            orientation: "vertical"
                            padding: "10dp"
                            spacing: "12dp"
                            size_hint_y: None
                            height: self.minimum_height
                    MDBoxLayout:
                        size_hint_y: None
                        height: "60dp"
                        md_bg_color: 0.12, 0.12, 0.18, 1
                        padding: "8dp"
                        spacing: "6dp"
                        MDTextField:
                            id: post_input
                            hint_text: "What's on your mind?"
                            mode: "round"
                            size_hint_x: 0.85
                            on_text_validate: app.create_post()
                        MDIconButton:
                            icon: "send"
                            theme_text_color: "Custom"
                            text_color: 0.42, 0.36, 0.91, 1
                            on_release: app.create_post()

            MDBottomNavigationItem:
                name: "tab_video"
                text: "Video"
                icon: "play-circle"
                MDBoxLayout:
                    orientation: "vertical"
                    MDTopAppBar:
                        title: "Videos"
                        md_bg_color: 0.12, 0.12, 0.18, 1
                        specific_text_color: 0.42, 0.36, 0.91, 1
                    MDLabel:
                        text: "No videos yet"
                        halign: "center"
                        theme_text_color: "Custom"
                        text_color: 0.63, 0.63, 0.69, 1

            MDBottomNavigationItem:
                name: "tab_add"
                text: "Add"
                icon: "plus-circle"
                MDBoxLayout:
                    orientation: "vertical"
                    MDTopAppBar:
                        title: "Create Post"
                        md_bg_color: 0.12, 0.12, 0.18, 1
                        specific_text_color: 0.42, 0.36, 0.91, 1
                    ScrollView:
                        MDBoxLayout:
                            orientation: "vertical"
                            padding: "15dp"
                            spacing: "15dp"
                            size_hint_y: None
                            height: self.minimum_height
                            MDTextField:
                                id: add_caption
                                hint_text: "What's on your mind?"
                                mode: "rectangle"
                                multiline: True
                                size_hint_y: None
                                height: "120dp"
                            MDBoxLayout:
                                size_hint_y: None
                                height: "60dp"
                                spacing: "5dp"
                                MDFlatButton:
                                    text: "Photo"
                                    theme_text_color: "Custom"
                                    text_color: 0.42, 0.36, 0.91, 1
                                    on_release: app.select_media("Photo")
                                MDFlatButton:
                                    text: "Video"
                                    theme_text_color: "Custom"
                                    text_color: 0.42, 0.36, 0.91, 1
                                    on_release: app.select_media("Video")
                            MDLabel:
                                id: add_preview
                                text: "No media selected"
                                halign: "center"
                                theme_text_color: "Custom"
                                text_color: 0.63, 0.63, 0.69, 1
                                size_hint_y: None
                                height: "30dp"
                            MDRaisedButton:
                                text: "POST"
                                size_hint_x: None
                                width: "300dp"
                                pos_hint: {"center_x": 0.5}
                                md_bg_color: 0.42, 0.36, 0.91, 1
                                on_release: app.add_post_from_tab()
                            MDLabel:
                                id: add_status
                                text: ""
                                halign: "center"
                                theme_text_color: "Custom"
                                text_color: 0.2, 0.9, 0.4, 1
                                size_hint_y: None
                                height: "30dp"

            MDBottomNavigationItem:
                name: "tab_shop"
                text: "Shop"
                icon: "shopping"
                MDBoxLayout:
                    orientation: "vertical"
                    MDTopAppBar:
                        title: "Nexus Market"
                        md_bg_color: 0.12, 0.12, 0.18, 1
                        specific_text_color: 0.42, 0.36, 0.91, 1
                    MDLabel:
                        text: "No products yet"
                        halign: "center"
                        theme_text_color: "Custom"
                        text_color: 0.63, 0.63, 0.69, 1

            MDBottomNavigationItem:
                name: "tab_chat"
                text: "Chat"
                icon: "message"
                MDBoxLayout:
                    orientation: "vertical"
                    MDTopAppBar:
                        title: "Messages"
                        md_bg_color: 0.12, 0.12, 0.18, 1
                        specific_text_color: 0.42, 0.36, 0.91, 1
                        right_action_items: [["plus", lambda x: app.new_chat_dialog()]]
                    ScrollView:
                        MDBoxLayout:
                            id: chat_list
                            orientation: "vertical"
                            padding: "10dp"
                            spacing: "8dp"
                            size_hint_y: None
                            height: self.minimum_height

            MDBottomNavigationItem:
                name: "tab_profile"
                text: "Profile"
                icon: "account"
                MDBoxLayout:
                    orientation: "vertical"
                    MDTopAppBar:
                        title: "Profile"
                        md_bg_color: 0.12, 0.12, 0.18, 1
                        specific_text_color: 0.42, 0.36, 0.91, 1
                        left_action_items: [["cog", lambda x: app.open_settings()]]
                        right_action_items: [["logout", lambda x: app.do_logout()]]
                    ScrollView:
                        MDBoxLayout:
                            orientation: "vertical"
                            padding: "15dp"
                            spacing: "15dp"
                            size_hint_y: None
                            height: self.minimum_height
                            MDBoxLayout:
                                size_hint_y: None
                                height: "110dp"
                                spacing: "15dp"
                                MDCard:
                                    size_hint: (None, None)
                                    size: "100dp", "100dp"
                                    radius: [50]
                                    md_bg_color: 0.42, 0.36, 0.91, 1
                                    MDLabel:
                                        id: profile_avatar
                                        text: "?"
                                        halign: "center"
                                        theme_text_color: "Custom"
                                        text_color: 1,1,1,1
                                        font_style: "H2"
                                MDBoxLayout:
                                    orientation: "vertical"
                                    spacing: "4dp"
                                    MDBoxLayout:
                                        size_hint_y: None
                                        height: "30dp"
                                        spacing: "5dp"
                                        MDLabel:
                                            id: profile_name
                                            text: "User"
                                            theme_text_color: "Custom"
                                            text_color: 1,1,1,1
                                            bold: True
                                            font_style: "H6"
                                        MDIconButton:
                                            id: profile_badge
                                            icon: "check-decagram"
                                            theme_text_color: "Custom"
                                            text_color: 0.3, 0.6, 1, 1
                                            icon_size: "20dp"
                                            opacity: 0
                                    MDLabel:
                                        id: profile_email
                                        text: "email@nexus.com"
                                        theme_text_color: "Custom"
                                        text_color: 0.63, 0.63, 0.69, 1
                                        size_hint_y: None
                                        height: "20dp"
                                    MDLabel:
                                        id: profile_uid
                                        text: ""
                                        theme_text_color: "Custom"
                                        text_color: 0.63, 0.63, 0.69, 1
                                        font_style: "Caption"
                                        size_hint_y: None
                                        height: "20dp"
                            MDCard:
                                size_hint_y: None
                                height: "70dp"
                                radius: [15]
                                md_bg_color: 0.12, 0.12, 0.18, 1
                                padding: "10dp"
                                MDBoxLayout:
                                    MDBoxLayout:
                                        orientation: "vertical"
                                        MDLabel:
                                            text: "0"
                                            halign: "center"
                                            theme_text_color: "Custom"
                                            text_color: 1,1,1,1
                                            bold: True
                                            font_style: "H6"
                                        MDLabel:
                                            text: "Posts"
                                            halign: "center"
                                            theme_text_color: "Custom"
                                            text_color: 0.63, 0.63, 0.69, 1
                                            font_style: "Caption"
                                    MDBoxLayout:
                                        orientation: "vertical"
                                        MDLabel:
                                            text: "0"
                                            halign: "center"
                                            theme_text_color: "Custom"
                                            text_color: 1,1,1,1
                                            bold: True
                                            font_style: "H6"
                                        MDLabel:
                                            text: "Followers"
                                            halign: "center"
                                            theme_text_color: "Custom"
                                            text_color: 0.63, 0.63, 0.69, 1
                                            font_style: "Caption"
                                    MDBoxLayout:
                                        orientation: "vertical"
                                        MDLabel:
                                            text: "0"
                                            halign: "center"
                                            theme_text_color: "Custom"
                                            text_color: 1,1,1,1
                                            bold: True
                                            font_style: "H6"
                                        MDLabel:
                                            text: "Following"
                                            halign: "center"
                                            theme_text_color: "Custom"
                                            text_color: 0.63, 0.63, 0.69, 1
                                            font_style: "Caption"
                            MDFlatButton:
                                text: "Edit Profile"
                                size_hint_x: None
                                width: "250dp"
                                pos_hint: {"center_x": 0.5}
                                theme_text_color: "Custom"
                                text_color: 0.42, 0.36, 0.91, 1
                                on_release: app.open_settings()

    MDScreen:
        id: chat_screen
        name: "chat_screen"
        md_bg_color: 0.06, 0.06, 0.1, 1
        pos_hint: {"x": -2, "y": 0}
        size_hint: (0, 0)
        MDBoxLayout:
            orientation: "vertical"
            MDTopAppBar:
                id: chat_header
                title: "Chat"
                md_bg_color: 0.12, 0.12, 0.18, 1
                specific_text_color: 0.42, 0.36, 0.91, 1
                left_action_items: [["arrow-left", lambda x: app.close_chat()]]
                right_action_items: [["phone", lambda x: app.audio_call()], ["video", lambda x: app.video_call()]]
            ScrollView:
                id: msg_scroll
                MDBoxLayout:
                    id: msg_container
                    orientation: "vertical"
                    padding: "10dp"
                    spacing: "8dp"
                    size_hint_y: None
                    height: self.minimum_height
            MDBoxLayout:
                size_hint_y: None
                height: "60dp"
                md_bg_color: 0.12, 0.12, 0.18, 1
                padding: "8dp"
                spacing: "6dp"
                MDTextField:
                    id: msg_input
                    hint_text: "Type a message..."
                    mode: "round"
                    size_hint_x: 0.85
                    on_text_validate: app.send_message()
                MDIconButton:
                    icon: "send"
                    theme_text_color: "Custom"
                    text_color: 0.42, 0.36, 0.91, 1
                    on_release: app.send_message()

    MDScreen:
        id: audio_call_screen
        name: "audio_call_screen"
        md_bg_color: 0.06, 0.06, 0.1, 1
        pos_hint: {"x": -2, "y": 0}
        size_hint: (0, 0)
        MDBoxLayout:
            orientation: "vertical"
            padding: "20dp"
            spacing: "20dp"
            Widget:
                size_hint_y: None
                height: "60dp"
            MDCard:
                size_hint: (None, None)
                size: "150dp", "150dp"
                radius: [75]
                md_bg_color: 0.42, 0.36, 0.91, 1
                pos_hint: {"center_x": 0.5}
                MDLabel:
                    id: audio_avatar
                    text: "?"
                    halign: "center"
                    theme_text_color: "Custom"
                    text_color: 1,1,1,1
                    font_style: "H2"
            MDLabel:
                id: audio_name
                text: "Calling..."
                halign: "center"
                theme_text_color: "Custom"
                text_color: 1,1,1,1
                font_style: "H5"
                size_hint_y: None
                height: "40dp"
            MDLabel:
                id: audio_status
                text: "Calling..."
                halign: "center"
                theme_text_color: "Custom"
                text_color: 0.63, 0.63, 0.69, 1
                size_hint_y: None
                height: "30dp"
            Widget:
            MDBoxLayout:
                size_hint_y: None
                height: "80dp"
                spacing: "15dp"
                padding: "10dp"
                MDIconButton:
                    id: mute_btn
                    icon: "microphone"
                    theme_text_color: "Custom"
                    text_color: 1,1,1,1
                    md_bg_color: 0.18, 0.18, 0.25, 1
                    on_release: app.toggle_mute()
                MDIconButton:
                    icon: "phone-hangup"
                    theme_text_color: "Custom"
                    text_color: 1,1,1,1
                    md_bg_color: 1, 0.3, 0.4, 1
                    on_release: app.end_call()
                MDIconButton:
                    id: speaker_btn
                    icon: "volume-high"
                    theme_text_color: "Custom"
                    text_color: 1,1,1,1
                    md_bg_color: 0.18, 0.18, 0.25, 1
                    on_release: app.toggle_speaker()

    MDScreen:
        id: video_call_screen
        name: "video_call_screen"
        md_bg_color: 0.02, 0.02, 0.05, 1
        pos_hint: {"x": -2, "y": 0}
        size_hint: (0, 0)
        MDBoxLayout:
            orientation: "vertical"
            MDCard:
                md_bg_color: 0.10, 0.10, 0.18, 1
                radius: [20]
                padding: "20dp"
                MDBoxLayout:
                    orientation: "vertical"
                    MDCard:
                        size_hint: (None, None)
                        size: "140dp", "140dp"
                        radius: [70]
                        md_bg_color: 0.42, 0.36, 0.91, 1
                        pos_hint: {"center_x": 0.5}
                        MDLabel:
                            id: video_avatar
                            text: "?"
                            halign: "center"
                            theme_text_color: "Custom"
                            text_color: 1,1,1,1
                            font_style: "H2"
                    Widget:
                    MDLabel:
                        id: video_name
                        text: "Calling..."
                        halign: "center"
                        theme_text_color: "Custom"
                        text_color: 1,1,1,1
                        font_style: "H5"
                        size_hint_y: None
                        height: "40dp"
                    MDLabel:
                        id: video_status
                        text: "Calling..."
                        halign: "center"
                        theme_text_color: "Custom"
                        text_color: 0.63, 0.63, 0.69, 1
                        size_hint_y: None
                        height: "30dp"
            MDBoxLayout:
                size_hint_y: None
                height: "100dp"
                spacing: "10dp"
                padding: "15dp"
                MDIconButton:
                    id: vmute_btn
                    icon: "microphone"
                    theme_text_color: "Custom"
                    text_color: 1,1,1,1
                    md_bg_color: 0.18, 0.18, 0.25, 1
                    on_release: app.toggle_mute()
                MDIconButton:
                    id: vcam_btn
                    icon: "video"
                    theme_text_color: "Custom"
                    text_color: 1,1,1,1
                    md_bg_color: 0.18, 0.18, 0.25, 1
                    on_release: app.toggle_camera()
                MDIconButton:
                    icon: "phone-hangup"
                    theme_text_color: "Custom"
                    text_color: 1,1,1,1
                    md_bg_color: 1, 0.3, 0.4, 1
                    on_release: app.end_call()
                MDIconButton:
                    id: vspeaker_btn
                    icon: "volume-high"
                    theme_text_color: "Custom"
                    text_color: 1,1,1,1
                    md_bg_color: 0.18, 0.18, 0.25, 1
                    on_release: app.toggle_speaker()

    MDScreen:
        id: notif_screen
        name: "notif_screen"
        md_bg_color: 0.06, 0.06, 0.1, 1
        pos_hint: {"x": -2, "y": 0}
        size_hint: (0, 0)
        MDBoxLayout:
            orientation: "vertical"
            MDTopAppBar:
                title: "Notifications"
                md_bg_color: 0.12, 0.12, 0.18, 1
                specific_text_color: 0.42, 0.36, 0.91, 1
                left_action_items: [["arrow-left", lambda x: app.close_notifications()]]
                right_action_items: [["check-all", lambda x: app.mark_all_notif_read()]]
            ScrollView:
                MDBoxLayout:
                    id: notif_list
                    orientation: "vertical"
                    padding: "10dp"
                    spacing: "8dp"
                    size_hint_y: None
                    height: self.minimum_height

    MDScreen:
        id: settings_screen
        name: "settings_screen"
        md_bg_color: 0.06, 0.06, 0.1, 1
        pos_hint: {"x": -2, "y": 0}
        size_hint: (0, 0)
        MDBoxLayout:
            orientation: "vertical"
            MDTopAppBar:
                title: "Settings"
                md_bg_color: 0.12, 0.12, 0.18, 1
                specific_text_color: 0.42, 0.36, 0.91, 1
                left_action_items: [["arrow-left", lambda x: app.close_settings()]]
            ScrollView:
                MDBoxLayout:
                    orientation: "vertical"
                    padding: "15dp"
                    spacing: "12dp"
                    size_hint_y: None
                    height: self.minimum_height

                    MDLabel:
                        text: "Account"
                        theme_text_color: "Custom"
                        text_color: 0.42, 0.36, 0.91, 1
                        bold: True
                        size_hint_y: None
                        height: "30dp"

                    MDCard:
                        size_hint_y: None
                        height: "60dp"
                        radius: [10]
                        md_bg_color: 0.12, 0.12, 0.18, 1
                        padding: "10dp"
                        MDBoxLayout:
                            MDLabel:
                                text: "Edit Name"
                                theme_text_color: "Custom"
                                text_color: 1,1,1,1
                            MDIconButton:
                                icon: "chevron-right"
                                theme_text_color: "Custom"
                                text_color: 0.63, 0.63, 0.69, 1
                                on_release: app.edit_name_dialog()

                    MDCard:
                        size_hint_y: None
                        height: "60dp"
                        radius: [10]
                        md_bg_color: 0.12, 0.12, 0.18, 1
                        padding: "10dp"
                        MDBoxLayout:
                            MDLabel:
                                id: settings_email
                                text: "email@nexus.com"
                                theme_text_color: "Custom"
                                text_color: 0.63, 0.63, 0.69, 1

                    MDLabel:
                        text: "Appearance"
                        theme_text_color: "Custom"
                        text_color: 0.42, 0.36, 0.91, 1
                        bold: True
                        size_hint_y: None
                        height: "30dp"

                    MDCard:
                        size_hint_y: None
                        height: "60dp"
                        radius: [10]
                        md_bg_color: 0.12, 0.12, 0.18, 1
                        padding: "10dp"
                        MDBoxLayout:
                            MDLabel:
                                text: "Dark Mode"
                                theme_text_color: "Custom"
                                text_color: 1,1,1,1
                            MDFlatButton:
                                id: dark_btn
                                text: "ON"
                                theme_text_color: "Custom"
                                text_color: 0.42, 0.36, 0.91, 1
                                on_release: app.toggle_theme()

                    MDCard:
                        size_hint_y: None
                        height: "60dp"
                        radius: [10]
                        md_bg_color: 0.12, 0.12, 0.18, 1
                        padding: "10dp"
                        MDBoxLayout:
                            MDLabel:
                                text: "Notifications"
                                theme_text_color: "Custom"
                                text_color: 1,1,1,1
                            MDFlatButton:
                                id: notif_toggle_btn
                                text: "ON"
                                theme_text_color: "Custom"
                                text_color: 0.42, 0.36, 0.91, 1
                                on_release: app.toggle_notifications()

                    MDLabel:
                        text: "About"
                        theme_text_color: "Custom"
                        text_color: 0.42, 0.36, 0.91, 1
                        bold: True
                        size_hint_y: None
                        height: "30dp"

                    MDCard:
                        size_hint_y: None
                        height: "60dp"
                        radius: [10]
                        md_bg_color: 0.12, 0.12, 0.18, 1
                        padding: "10dp"
                        MDBoxLayout:
                            MDLabel:
                                text: "Version"
                                theme_text_color: "Custom"
                                text_color: 1,1,1,1
                            MDLabel:
                                text: "3.0.0"
                                halign: "right"
                                theme_text_color: "Custom"
                                text_color: 0.63, 0.63, 0.69, 1

                    MDRaisedButton:
                        text: "LOGOUT"
                        size_hint_x: None
                        width: "250dp"
                        pos_hint: {"center_x": 0.5}
                        md_bg_color: 1, 0.3, 0.4, 1
                        on_release: app.do_logout()
'''


# ============================================================
# MAIN APP
# ============================================================
class NexusApp(MDApp):
    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "DeepPurple"

        print(f"Firebase: {FIREBASE_PROJECT_ID}")
        self.auth = FirebaseAuth(FIREBASE_API_KEY)
        self.fs = FirestoreDB(FIREBASE_PROJECT_ID)
        self.db = LocalDB()
        self.notif = NotificationManager()
        self.current_user = None
        self.current_chat = None
        self.user_profile = {}
        self.call_timer = None
        self.call_seconds = 0
        self.muted = False
        self.speaker_on = True
        self.camera_on = True
        self.selected_media = "Photo"
        self.dark_mode = True
        self.notifications_on = True

        return Builder.load_string(KV)

    def on_start(self):
        Clock.schedule_once(lambda dt: self.check_auto_login(), 0.5)

    def check_auto_login(self):
        user = self.auth.load_session()
        if user:
            self.current_user = user
            self.fs.set_token(user["idToken"])
            self.root.current = "home"
            self.load_user_profile(user["localId"])
            print(f"Auto-login: {user['email']}")
            Clock.schedule_once(lambda dt: self.load_posts(), 0.5)
            Clock.schedule_once(lambda dt: self.load_chat_list(), 0.7)
            Clock.schedule_once(lambda dt: self.add_welcome_notif(), 1.5)
        else:
            self.root.current = "login"

    def add_welcome_notif(self):
        self.notif.add("Welcome to Nexus!",
                       "Your account is ready", "success")
        self.load_notifications()

    def load_user_profile(self, uid):
        try:
            ok, profile = self.fs.get_user_profile(uid)
            if ok and profile:
                self.user_profile = profile
                name = profile.get("name", self.current_user["email"].split("@")[0])
                self.root.ids.profile_name.text = name
                self.root.ids.profile_avatar.text = name[0].upper() if name else "?"
                self.root.ids.profile_email.text = self.current_user["email"]
                self.root.ids.profile_uid.text = f"ID: {uid[:12]}..."
                self.root.ids.settings_email.text = self.current_user["email"]

                is_verified = profile.get("verified", False)
                if is_verified:
                    self.root.ids.profile_badge.opacity = 1
                    print(f"Verified: {name}")
                else:
                    self.root.ids.profile_badge.opacity = 0
            else:
                email = self.current_user["email"]
                self.root.ids.profile_email.text = email
                self.root.ids.profile_uid.text = f"ID: {uid[:12]}..."
                self.root.ids.settings_email.text = email
        except Exception as e:
            print(f"Profile load error: {e}")

    def go_screen(self, name):
        self.root.current = name

    def do_login(self):
        email = self.root.ids.login_email.text.strip()
        password = self.root.ids.login_password.text
        if not email or not password:
            self.set_status("login_status", "Email & Password din")
            return
        self.set_status("login_status", "Checking...",
                       color=(0.42, 0.36, 0.91, 1))
        ok, msg, user = self.auth.login(email, password)
        if ok:
            self.set_status("login_status", msg, color=(0.2, 0.9, 0.4, 1))
            self.current_user = user
            self.auth.save_session(user)
            self.fs.set_token(user["idToken"])
            Clock.schedule_once(lambda dt: self.after_login(user), 0.8)
        else:
            self.set_status("login_status", msg)

    def after_login(self, user):
        self.root.current = "home"
        self.load_user_profile(user["localId"])
        self.root.ids.login_email.text = ""
        self.root.ids.login_password.text = ""
        self.root.ids.login_status.text = ""
        self.load_posts()
        self.load_chat_list()
        self.add_welcome_notif()

    def do_signup(self):
        name = self.root.ids.su_name.text.strip()
        email = self.root.ids.su_email.text.strip()
        password = self.root.ids.su_password.text
        confirm = self.root.ids.su_confirm.text

        valid, msg = NameValidator.is_valid(name)
        if not valid:
            self.set_status("su_status", msg)
            return

        if not email or "@" not in email:
            self.set_status("su_status", "Sothik Email din")
            return

        if password != confirm:
            self.set_status("su_status", "Password milche na")
            return

        if len(password) < 8:
            self.set_status("su_status", "Password kompokkhe 8 okkhor")
            return
        if not re.search(r'[A-Za-z]', password):
            self.set_status("su_status", "Password e okkhor thakte hobe")
            return
        if not re.search(r'[0-9]', password):
            self.set_status("su_status", "Password e number thakte hobe")
            return

        self.set_status("su_status", "Creating account...",
                       color=(0.42, 0.36, 0.91, 1))

        ok, msg, res = self.auth.signup(email, password)
        if ok:
            uid = res["localId"]
            self.fs.set_token(res["idToken"])
            profile_data = {
                "name": name,
                "email": email,
                "verified": False,
                "created_at": datetime.now().isoformat(),
            }
            self.fs.save_user_profile(uid, profile_data)
            print(f"Profile saved: {name}")

            self.set_status("su_status", "Account created! Login now",
                          color=(0.2, 0.9, 0.4, 1))
            self.root.ids.su_name.text = ""
            self.root.ids.su_email.text = ""
            self.root.ids.su_password.text = ""
            self.root.ids.su_confirm.text = ""
            Clock.schedule_once(lambda dt: self.go_screen("login"), 1.5)
        else:
            self.set_status("su_status", msg)

    def create_post(self):
        try:
            text = self.root.ids.post_input.text.strip()
            if not text or not self.current_user:
                return
            safe, issues = ContentGuard.check(text)
            if not safe:
                print(f"Flagged: {issues}")
                self.root.ids.post_input.text = ""
                return
            post_data = {
                "userId": self.current_user["localId"],
                "email": self.current_user["email"],
                "name": self.user_profile.get("name", ""),
                "verified": self.user_profile.get("verified", False),
                "text": text,
                "likes": 0,
                "timestamp": datetime.now().isoformat(),
            }
            ok, res = self.fs.add_post(post_data)
            if ok:
                print("Post saved")
                self.root.ids.post_input.text = ""
                self.notif.add("Post Published", "Your post is live", "success")
                Clock.schedule_once(lambda dt: self.load_posts(), 0.3)
            else:
                print(f"Post error: {res}")
        except Exception as e:
            print(f"POST ERROR: {e}")

    def add_post_from_tab(self):
        try:
            text = self.root.ids.add_caption.text.strip()
            if not text or not self.current_user:
                self.root.ids.add_status.text = "Lik hun kichu!"
                return
            post_data = {
                "userId": self.current_user["localId"],
                "email": self.current_user["email"],
                "name": self.user_profile.get("name", ""),
                "verified": self.user_profile.get("verified", False),
                "text": f"[{self.selected_media}] {text}",
                "likes": 0,
                "timestamp": datetime.now().isoformat(),
            }
            ok, res = self.fs.add_post(post_data)
            if ok:
                self.root.ids.add_status.text = "Posted!"
                self.root.ids.add_status.text_color = (0.2, 0.9, 0.4, 1)
                self.root.ids.add_caption.text = ""
                self.root.ids.add_preview.text = "No media selected"
                self.notif.add("Post Published", "Your post is live", "success")
                Clock.schedule_once(lambda dt: self.load_posts(), 0.3)
                Clock.schedule_once(lambda dt: self.clear_add_status(), 2)
            else:
                self.root.ids.add_status.text = "Error!"
        except Exception as e:
            print(f"ADD POST ERROR: {e}")

    def clear_add_status(self):
        try:
            self.root.ids.add_status.text = ""
        except:
            pass

    def select_media(self, media):
        self.selected_media = media
        try:
            self.root.ids.add_preview.text = f"Selected: {media}"
            self.root.ids.add_preview.text_color = (0.42, 0.36, 0.91, 1)
        except:
            pass

    def load_posts(self):
        try:
            feed = self.root.ids.feed
            feed.clear_widgets()
            ok, posts = self.fs.get_posts()
            if not ok or not posts:
                feed.add_widget(MDLabel(
                    text="No posts yet",
                    halign="center",
                    theme_text_color="Custom",
                    text_color=(0.63, 0.63, 0.69, 1),
                    size_hint_y=None, height=dp(80),
                ))
                return
            posts.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            for post in posts:
                card = MDCard(
                    size_hint_y=None, height=dp(140),
                    radius=[dp(15)],
                    md_bg_color=(0.12, 0.12, 0.18, 1),
                    padding=dp(12),
                )
                col = MDBoxLayout(orientation="vertical", spacing=dp(4))

                header = MDBoxLayout(size_hint_y=None, height=dp(26), spacing=dp(5))
                poster_name = post.get("name") or post.get("email", "?")
                header.add_widget(MDLabel(
                    text=poster_name,
                    theme_text_color="Custom",
                    text_color=(1, 1, 1, 1),
                    bold=True,
                    size_hint_y=None, height=dp(24),
                ))
                if post.get("verified", False):
                    header.add_widget(MDIconButton(
                        icon="check-decagram",
                        theme_text_color="Custom",
                        text_color=(0.3, 0.6, 1, 1),
                        icon_size="18dp",
                        size_hint_x=None,
                        width=dp(30),
                    ))
                col.add_widget(header)
                col.add_widget(MDLabel(
                    text=post.get("text", ""),
                    theme_text_color="Custom",
                    text_color=(0.9, 0.9, 0.9, 1),
                ))
                card.add_widget(col)
                feed.add_widget(card)
        except Exception as e:
            print(f"LOAD ERROR: {e}")

    def load_chat_list(self):
        try:
            chat_list = self.root.ids.chat_list
            chat_list.clear_widgets()
            chats = self.db.get_chats()
            if not chats:
                chat_list.add_widget(MDLabel(
                    text="No chats yet. Tap + to start",
                    halign="center",
                    theme_text_color="Custom",
                    text_color=(0.63, 0.63, 0.69, 1),
                    size_hint_y=None, height=dp(80),
                ))
                return
            for name, last_msg, time, unread in chats:
                card = MDCard(
                    size_hint_y=None, height=dp(70),
                    radius=[dp(12)],
                    md_bg_color=(0.12, 0.12, 0.18, 1),
                    padding=dp(10),
                )
                row = MDBoxLayout(spacing=dp(10))
                avatar = MDCard(
                    size_hint=(None, None),
                    size=(dp(50), dp(50)),
                    radius=[dp(25)],
                    md_bg_color=(0.42, 0.36, 0.91, 1),
                )
                avatar.add_widget(MDLabel(
                    text=name[0].upper(),
                    halign="center",
                    theme_text_color="Custom",
                    text_color=(1, 1, 1, 1),
                    font_style="H6",
                ))
                mid = MDBoxLayout(orientation="vertical", spacing=dp(2))
                mid.add_widget(MDLabel(
                    text=name,
                    theme_text_color="Custom",
                    text_color=(1, 1, 1, 1),
                    bold=True,
                    size_hint_y=None, height=dp(24),
                ))
                mid.add_widget(MDLabel(
                    text=last_msg if last_msg else "Tap to chat",
                    theme_text_color="Custom",
                    text_color=(0.63, 0.63, 0.69, 1),
                    font_style="Caption",
                    size_hint_y=None, height=dp(20),
                ))
                row.add_widget(avatar)
                row.add_widget(mid)
                card.add_widget(row)
                card.name = name
                def make_h(n):
                    def h(inst, touch):
                        if inst.collide_point(*touch.pos):
                            self.open_chat(n)
                    return h
                card.on_touch_up = make_h(name)
                chat_list.add_widget(card)
        except Exception as e:
            print(f"CHAT LIST ERROR: {e}")

    def new_chat_dialog(self):
        try:
            from kivymd.uix.dialog import MDDialog
            self.name_field = MDTextField(hint_text="Name", mode="rectangle")
            dlg = MDDialog(
                title="New Chat",
                type="custom",
                content_cls=self.name_field,
                buttons=[
                    MDFlatButton(text="CANCEL",
                                on_release=lambda x: dlg.dismiss()),
                    MDFlatButton(text="START",
                                on_release=lambda x: self.create_chat(dlg)),
                ],
            )
            dlg.open()
        except Exception as e:
            print(f"NEW CHAT ERROR: {e}")

    def create_chat(self, dlg):
        try:
            name = self.name_field.text.strip()
            if not name:
                dlg.dismiss()
                return
            self.db.ensure_chat(name)
            self.load_chat_list()
            dlg.dismiss()
            print(f"Chat created: {name}")
        except Exception as e:
            print(f"CREATE CHAT ERROR: {e}")

    def open_chat(self, name):
        try:
            self.current_chat = name
            self.db.reset_unread(name)
            self.load_chat_list()
            self.root.ids.chat_screen.pos_hint = {"x": 0, "y": 0}
            self.root.ids.chat_screen.size_hint = (1, 1)
            self.root.ids.chat_header.title = name
            self.root.ids.msg_container.clear_widgets()
            messages = self.db.get_messages(name)
            if not messages:
                self.add_bubble("Say hi!", is_me=False)
            for text, is_me, time in messages:
                self.add_bubble(text, bool(is_me), time)
        except Exception as e:
            print(f"OPEN CHAT ERROR: {e}")

    def add_bubble(self, text, is_me, time=""):
        try:
            c = MDBoxLayout(size_hint_y=None, height=dp(70))
            c.add_widget(MessageBubble(text=text, is_me=is_me, time=time))
            self.root.ids.msg_container.add_widget(c)
        except Exception as e:
            print(f"BUBBLE ERROR: {e}")

    def send_message(self):
        try:
            text = self.root.ids.msg_input.text.strip()
            if not text or not self.current_chat:
                return
            self.db.add_message(self.current_chat, text, True)
            self.db.update_chat(self.current_chat, text, "now")
            self.add_bubble(text, is_me=True, time="now")
            self.root.ids.msg_input.text = ""
            self.load_chat_list()
        except Exception as e:
            print(f"SEND ERROR: {e}")

    def close_chat(self):
        try:
            self.root.ids.chat_screen.pos_hint = {"x": -2, "y": 0}
            self.root.ids.chat_screen.size_hint = (0, 0)
            self.current_chat = None
        except:
            pass

    def audio_call(self):
        try:
            name = self.current_chat or "Unknown"
            self.root.ids.audio_name.text = name
            self.root.ids.audio_avatar.text = name[0].upper()
            self.root.ids.audio_status.text = "Calling..."
            self.root.ids.audio_call_screen.pos_hint = {"x": 0, "y": 0}
            self.root.ids.audio_call_screen.size_hint = (1, 1)
            self.call_seconds = 0
            Clock.schedule_once(self.start_call_timer, 2)
            self.notif.add("Audio Call", f"Calling {name}", "call")
        except Exception as e:
            print(f"AUDIO ERROR: {e}")

    def start_call_timer(self, dt):
        try:
            self.root.ids.audio_status.text = "00:00"
            self.root.ids.video_status.text = "00:00"
            self.call_timer = Clock.schedule_interval(self.tick_timer, 1)
        except:
            pass

    def tick_timer(self, dt):
        self.call_seconds += 1
        m, s = divmod(self.call_seconds, 60)
        text = f"{m:02d}:{s:02d}"
        try:
            self.root.ids.audio_status.text = text
            self.root.ids.video_status.text = text
        except:
            pass

    def video_call(self):
        try:
            name = self.current_chat or "Unknown"
            self.root.ids.video_name.text = name
            self.root.ids.video_avatar.text = name[0].upper()
            self.root.ids.video_status.text = "Calling..."
            self.root.ids.video_call_screen.pos_hint = {"x": 0, "y": 0}
            self.root.ids.video_call_screen.size_hint = (1, 1)
            self.call_seconds = 0
            Clock.schedule_once(self.start_call_timer, 2)
            self.notif.add("Video Call", f"Calling {name}", "call")
        except Exception as e:
            print(f"VIDEO CALL ERROR: {e}")

    def toggle_mute(self):
        self.muted = not self.muted
        icon = "microphone-off" if self.muted else "microphone"
        try:
            self.root.ids.mute_btn.icon = icon
            self.root.ids.vmute_btn.icon = icon
        except:
            pass

    def toggle_speaker(self):
        self.speaker_on = not self.speaker_on
        icon = "volume-high" if self.speaker_on else "volume-off"
        try:
            self.root.ids.speaker_btn.icon = icon
            self.root.ids.vspeaker_btn.icon = icon
        except:
            pass

    def toggle_camera(self):
        self.camera_on = not self.camera_on
        try:
            self.root.ids.vcam_btn.icon = "video" if self.camera_on else "video-off"
        except:
            pass

    def end_call(self):
        try:
            if self.call_timer:
                self.call_timer.cancel()
                self.call_timer = None
            self.call_seconds = 0
            self.root.ids.audio_call_screen.pos_hint = {"x": -2, "y": 0}
            self.root.ids.audio_call_screen.size_hint = (0, 0)
            self.root.ids.video_call_screen.pos_hint = {"x": -2, "y": 0}
            self.root.ids.video_call_screen.size_hint = (0, 0)
        except:
            pass

    def open_notifications(self):
        try:
            self.notif.mark_all_read()
            self.load_notifications()
            self.root.ids.notif_screen.pos_hint = {"x": 0, "y": 0}
            self.root.ids.notif_screen.size_hint = (1, 1)
        except Exception as e:
            print(f"NOTIF ERROR: {e}")

    def close_notifications(self):
        try:
            self.root.ids.notif_screen.pos_hint = {"x": -2, "y": 0}
            self.root.ids.notif_screen.size_hint = (0, 0)
        except:
            pass

    def load_notifications(self):
        try:
            container = self.root.ids.notif_list
            container.clear_widgets()
            all_notifs = self.notif.get_all()
            if not all_notifs:
                container.add_widget(MDLabel(
                    text="No notifications",
                    halign="center",
                    theme_text_color="Custom",
                    text_color=(0.63, 0.63, 0.69, 1),
                    size_hint_y=None, height=dp(80),
                ))
                return
            for n in all_notifs:
                card = MDCard(
                    size_hint_y=None, height=dp(90),
                    radius=[dp(12)],
                    md_bg_color=(0.12, 0.12, 0.18, 1),
                    padding=dp(12),
                )
                col = MDBoxLayout(orientation="vertical", spacing=dp(3))
                top = MDBoxLayout(size_hint_y=None, height=dp(24))
                top.add_widget(MDLabel(
                    text=n["title"],
                    theme_text_color="Custom",
                    text_color=(1, 1, 1, 1),
                    bold=True,
                ))
                top.add_widget(MDLabel(
                    text=n["time"],
                    halign="right",
                    theme_text_color="Custom",
                    text_color=(0.63, 0.63, 0.69, 1),
                    font_style="Caption",
                    size_hint_x=None, width=dp(50),
                ))
                col.add_widget(top)
                col.add_widget(MDLabel(
                    text=n["message"],
                    theme_text_color="Custom",
                    text_color=(0.8, 0.8, 0.8, 1),
                    font_style="Caption",
                ))
                card.add_widget(col)
                container.add_widget(card)
        except Exception as e:
            print(f"LOAD NOTIF ERROR: {e}")

    def mark_all_notif_read(self):
        self.notif.mark_all_read()
        self.load_notifications()

    def open_settings(self):
        try:
            self.root.ids.settings_screen.pos_hint = {"x": 0, "y": 0}
            self.root.ids.settings_screen.size_hint = (1, 1)
        except Exception as e:
            print(f"SETTINGS ERROR: {e}")

    def close_settings(self):
        try:
            self.root.ids.settings_screen.pos_hint = {"x": -2, "y": 0}
            self.root.ids.settings_screen.size_hint = (0, 0)
        except:
            pass

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        try:
            if self.dark_mode:
                self.theme_cls.theme_style = "Dark"
                self.root.ids.dark_btn.text = "ON"
                Window.clearcolor = (0.06, 0.06, 0.1, 1)
            else:
                self.theme_cls.theme_style = "Light"
                self.root.ids.dark_btn.text = "OFF"
                Window.clearcolor = (0.95, 0.95, 0.95, 1)
        except Exception as e:
            print(f"THEME ERROR: {e}")

    def toggle_notifications(self):
        self.notifications_on = not self.notifications_on
        try:
            self.root.ids.notif_toggle_btn.text = "ON" if self.notifications_on else "OFF"
        except:
            pass

    def edit_name_dialog(self):
        try:
            from kivymd.uix.dialog import MDDialog
            self.edit_name_field = MDTextField(
                hint_text="New Name",
                text=self.user_profile.get("name", ""),
                mode="rectangle",
            )
            dlg = MDDialog(
                title="Edit Name",
                type="custom",
                content_cls=self.edit_name_field,
                buttons=[
                    MDFlatButton(text="CANCEL",
                                on_release=lambda x: dlg.dismiss()),
                    MDFlatButton(text="SAVE",
                                on_release=lambda x: self.save_new_name(dlg)),
                ],
            )
            dlg.open()
        except Exception as e:
            print(f"EDIT NAME ERROR: {e}")

    def save_new_name(self, dlg):
        try:
            new_name = self.edit_name_field.text.strip()
            valid, msg = NameValidator.is_valid(new_name)
            if not valid:
                print(f"Invalid: {msg}")
                dlg.dismiss()
                return
            uid = self.current_user["localId"]
            self.fs.save_user_profile(uid, {"name": new_name})
            self.user_profile["name"] = new_name
            self.root.ids.profile_name.text = new_name
            self.root.ids.profile_avatar.text = new_name[0].upper()
            self.notif.add("Name Updated", f"Now: {new_name}", "success")
            dlg.dismiss()
            print(f"Name: {new_name}")
        except Exception as e:
            print(f"SAVE NAME ERROR: {e}")

    def do_logout(self):
        self.auth.clear_session()
        self.current_user = None
        self.user_profile = {}
        self.root.current = "login"
        try:
            self.root.ids.login_status.text = ""
        except:
            pass
        print("Logged out")

    def set_status(self, label_id, text, color=(1, 0.4, 0.4, 1)):
        try:
            lbl = self.root.ids[label_id]
            lbl.text = text
            lbl.text_color = color
        except:
            pass

    def on_stop(self):
        try:
            self.db.close()
        except:
            pass


if __name__ == "__main__":
    NexusApp().run()