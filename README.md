# 🔮 AutoMod by Jazzzzz

**AutoMod** is a fully automated moderation system designed for **HexChat**, written in **Python**.
It intelligently detects and handles abusive users, bad nicknames, offensive words, and flooding behavior — all with custom kick/ban messages, timed unbans, and per-channel protection.

---

### ✨ Key Features

* 🚫 Auto Kick + Ban for bad nicks, offensive words, or spam
* 🕒 Automatic unban timer (customizable per rule)
* 🧩 Wildcard nick detection (e.g. `*rambo*`)
* 🔐 Channel-specific protection (not global)
* 💾 Persistent configuration between restarts
* 🧠 Smart log system with timestamps
* 🧰 Real-time command control via chat (`/AMADD`, `/AMCHAN`, `/AMDEL`, `/AMLIST`, etc.)
* 🧑‍💻 Optional **Admin-only** command mode
* 💬 Text-based “popup” interface for Flatpak HexChat

---

### 🧱 Requirements

* HexChat (tested on Ubuntu Flatpak version)
* Python interface enabled (`/py list` should work)

---

### ⚙️ Installation

1. Copy `auto_mod_final_v1.0_wildban.py` into your addons folder:

   ```
   ~/.var/app/io.github.Hexchat/config/hexchat/addons/
   ```
2. Load it in HexChat:

   ```
   /py load auto_mod_final_v1.0_wildban.py
   ```
3. AutoMod will initialize and create its config + log files automatically.

---

### 📖 Documentation

Full usage instructions and command examples are available in:

* `AutoMod_README.txt` (detailed)
* `AutoMod_QuickGuide.txt` (short version for ops)

---

### 💜 Credits

Developed & fine-tuned by **Jazzzzz**
Built for DALnet & Bahamut IRCD network moderation enthusiasts
Tested on Ubuntu + Flatpak HexChat

---

> Keep your IRC channels clean, friendly, and fun —
> AutoMod watches your back so you can enjoy the chat ✨
