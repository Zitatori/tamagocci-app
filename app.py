# app.py
from tkinter import Tk, Canvas
from PIL import Image, ImageTk
import json, os, time
from random import random

SAVE_FILE = "save.json"

# ====== 調整パラメータ ======
DEBUG_OVERLAY = False        # 当たり枠を表示
CHAR_SCALE    = 0.40         # キャラの相対サイズ
BAR_HEIGHT    = 25           # ステータスバー高さ

# 画面窓（frame.png に対する割合）
R_SCREEN_LEFT = 0.300
R_SCREEN_TOP  = 0.290
R_SCREEN_W    = 0.400
R_SCREEN_H    = 0.330

# 本体ボタン（frame.png に対する割合）
R_BTN_R  = 0.040                            # 半径
R_BTN_Y  = 0.710                            # y（小さいほど上）
R_BTN_XS = (0.360, 0.500, 0.650)            # 左・OK・右のx

# ====== 画像ユーティリティ ======
def load_img(path, size=None, nearest=False):
    img = Image.open(path)
    if size:
        img = img.resize(size, Image.NEAREST if nearest else Image.LANCZOS)
    return ImageTk.PhotoImage(img)

def safe_load_img(path, size=None, nearest=False):
    try:
        return load_img(path, size, nearest)
    except Exception:
        return None


class TamaApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ゆるキャラたまごっち")

        # -------- フレーム＆キャンバス --------
        self.frame_pil = Image.open("images/frame.png")
        W, H = self.frame_pil.size
        self.canvas = Canvas(root, width=W, height=H, highlightthickness=0)
        self.canvas.pack()

        # 背景（任意）
        self.bg_tk = safe_load_img("images/background.png", size=(W, H))
        if self.bg_tk:
            self.canvas.create_image(0, 0, image=self.bg_tk, anchor="nw")

        self.frame_tk = ImageTk.PhotoImage(self.frame_pil)
        self.canvas.create_image(0, 0, image=self.frame_tk, anchor="nw")

        # -------- 画面窓の実ピクセル --------
        self.SCREEN_LEFT = int(W * R_SCREEN_LEFT)
        self.SCREEN_TOP  = int(H * R_SCREEN_TOP)
        self.SCREEN_W    = int(W * R_SCREEN_W)
        self.SCREEN_H    = int(H * R_SCREEN_H)

        # -------- ボタン定義 --------
        r_btn = int(min(W, H) * R_BTN_R)
        self.buttons = [
            {"name": "LEFT",  "cx": int(W*R_BTN_XS[0]), "cy": int(H*R_BTN_Y), "r": r_btn, "label": "L=🍙"},
            {"name": "OK",    "cx": int(W*R_BTN_XS[1]), "cy": int(H*R_BTN_Y), "r": r_btn, "label": "OK=🧩"},
            {"name": "RIGHT", "cx": int(W*R_BTN_XS[2]), "cy": int(H*R_BTN_Y), "r": r_btn, "label": "R=🧻"},
        ]

        # -------- 画像群 --------
        char_edge = int((min(self.SCREEN_W, self.SCREEN_H) - 20) * CHAR_SCALE)
        char_size = (char_edge, char_edge)
        self.imgs = {
            "happy":   safe_load_img("images/happy.png",   char_size, nearest=True),
            "hungry":  safe_load_img("images/hungry.png",  char_size, nearest=True),
            "sleepy":  safe_load_img("images/sleepy.png",  char_size, nearest=True),
            "poop":    safe_load_img("images/poop.png",    (int(W*0.06), int(W*0.06)), nearest=True),
            "onigiri": safe_load_img("images/onigiri.png", (int(W*0.10), int(W*0.10)), nearest=True),
            "block":   safe_load_img("images/block.png",   (int(W*0.12), int(W*0.12)), nearest=True),  # ← 追加
        }
        if not all([self.imgs["happy"], self.imgs["hungry"], self.imgs["sleepy"]]):
            raise RuntimeError("images/happy.png, hungry.png, sleepy.png を用意してね。")

        # キャラ配置（さらに下げたいなら +値を大きく）
        cx = self.SCREEN_LEFT + self.SCREEN_W//2
        cy = self.SCREEN_TOP + self.SCREEN_H//2 + 100
        self.char_id = self.canvas.create_image(cx, cy, image=self.imgs["happy"])

        # -------- ステータス --------
        self.stats = {
            "hunger": 80, "fun": 80, "clean": 80,
            "last_tick": time.time(), "lifetime_sec": 0,
        }
        self.poops = []

        # ステータスバー：画面窓 内・最上段
        PAD = 8
        self.bar_area = (
            self.SCREEN_LEFT + PAD,
            self.SCREEN_TOP  + PAD,
            self.SCREEN_LEFT + self.SCREEN_W - PAD,
            self.SCREEN_TOP  + PAD + BAR_HEIGHT
        )
        self.bar_ids = {"hunger": None, "fun": None, "clean": None}
        self.draw_bars()

        # 操作ガイド
        self.help_id = self.canvas.create_text(
            self.SCREEN_LEFT + self.SCREEN_W//3,
            self.SCREEN_TOP + self.SCREEN_H,
            text="左=🍙ごはん / 中=🧩あそぶ / 右=🧻おそうじ",
            fill="#333", font=("Arial", 14)
        )

        # クリック
        self.canvas.bind("<Button-1>", self.on_click)

        # 給餌状態
        self.feeding = {"active": False, "step": 0, "food_id": None, "next_tick": 0, "cooldown_until": 0}

        # ★あそぶ（積み木）状態 ← 追加
        self.playing = {"active": False, "step": 0, "obj_id": None, "next_tick": 0}

        # セーブ読み込み
        self.load()

        if DEBUG_OVERLAY:
            self.debug_overlay()

        self.tick()

    # ===== ステータスバー =====
    def draw_bars(self):
        x1, y1, x2, y2 = self.bar_area
        w = x2 - x1
        h = y2 - y1
        gap = 4
        seg_h = (h - 2*gap) // 3

        def draw_one(v, row, color):
            top = y1 + row*(seg_h+gap)
            full = self.canvas.create_rectangle(x1, top, x2, top+seg_h, outline="#dddddd")
            # BUG修正：/50 だと半分までしか伸びなかった→ /100 に戻す
            fill_w = int(w * max(0, min(100, v)) / 100)
            fill = self.canvas.create_rectangle(x1, top, x1+fill_w, top+seg_h, fill=color, width=0)
            return (full, fill)

        for k, rid in list(self.bar_ids.items()):
            if isinstance(rid, tuple):
                for iid in rid:
                    self.canvas.delete(iid)

        self.bar_ids["hunger"] = draw_one(self.stats["hunger"], 0, "#ffb3b3")
        self.bar_ids["fun"]    = draw_one(self.stats["fun"],    1, "#b3d4ff")
        self.bar_ids["clean"]  = draw_one(self.stats["clean"],  2, "#b3ffcc")

    def update_bars(self):
        self.draw_bars()

    # ===== デバッグオーバーレイ =====
    def debug_overlay(self):
        x, y, w, h = self.SCREEN_LEFT, self.SCREEN_TOP, self.SCREEN_W, self.SCREEN_H
        self.canvas.create_rectangle(x, y, x+w, y+h, outline="#00c8ff", width=2)
        self.canvas.create_text(x+6, y+12, text="SCREEN", fill="#00a0d0", anchor="w", font=("Arial", 10, "bold"))
        for b in self.buttons:
            self.canvas.create_oval(b["cx"]-b["r"], b["cy"]-b["r"], b["cx"]+b["r"], b["cy"]+b["r"],
                                    outline="#ff00aa", width=2)
            self.canvas.create_text(b["cx"], b["cy"], text=b["label"], fill="#ff00aa", font=("Arial", 10, "bold"))

    # ===== トースト =====
    def toast(self, msg, ms=1200):
        if hasattr(self, "toast_id") and self.toast_id:
            self.canvas.delete(self.toast_id)
        self.toast_id = self.canvas.create_text(
            self.SCREEN_LEFT + self.SCREEN_W//2,
            self.SCREEN_TOP + 18,
            text=msg, fill="#000", font=("Arial", 18, "bold")
        )
        self.root.after(ms, lambda: (self.canvas.delete(self.toast_id) if getattr(self, "toast_id", None) else None))

    # ===== 入力 =====
    def on_click(self, ev):
        if DEBUG_OVERLAY:
            print(f"[CLICK] x={ev.x}, y={ev.y}")
        # 演出中は無視（重ね実行を防ぐ）
        if self.feeding["active"] or self.playing["active"]:
            return
        # ボタン
        for b in self.buttons:
            if (ev.x - b["cx"])**2 + (ev.y - b["cy"])**2 <= b["r"]**2:
                self.handle_button(b["name"])
                return
        # うんち直クリック掃除
        for po in list(self.poops):
            bbox = self.canvas.bbox(po)
            if bbox and (bbox[0] <= ev.x <= bbox[2]) and (bbox[1] <= ev.y <= bbox[3]):
                self.clean_poop(po)
                return

    # ===== 3ボタン＝3機能 =====
    def handle_button(self, name):
        if name == "LEFT":  # ごはん
            now = time.time()
            if now < self.feeding["cooldown_until"]:
                self.toast("ちょっと待って〜⏳")
                return
            self.start_feeding()
            return

        if name == "OK":    # あそぶ（積み木）
            if not self.playing["active"]:
                self.start_playing()
            return

        if name == "RIGHT": # おそうじ
            for po in list(self.poops):
                self.clean_poop(po)
            self.stats["clean"] = min(100, self.stats["clean"] + 20)
            self.set_face("happy"); self.update_bars(); self.save()
            self.toast("ピカピカ🧻")
            return

    # ===== 給餌演出 =====
    def start_feeding(self):
        x = self.SCREEN_LEFT + self.SCREEN_W//2
        y = self.SCREEN_TOP  + self.SCREEN_H - int(self.SCREEN_H*0.08)
        if self.imgs["onigiri"]:
            food_id = self.canvas.create_image(x, y, image=self.imgs["onigiri"])
        else:
            food_id = self.canvas.create_text(x, y, text="🍙", font=("Arial", 32))
        self.feeding.update({"active": True, "step": 0, "food_id": food_id, "next_tick": time.time() + 0.35})
        self.set_face("happy"); self.toast("もぐもぐ🍙", ms=700)

    def tick_feeding(self):
        if not self.feeding["active"]:
            return
        now = time.time()
        if now < self.feeding["next_tick"]:
            return
        self.feeding["step"] += 1
        self.feeding["next_tick"] = now + 0.35
        dy = -4 if (self.feeding["step"] % 2 == 1) else 4
        self.canvas.move(self.char_id, 0, dy)
        if self.feeding["step"] >= 3:
            self.end_feeding()

    def end_feeding(self):
        if self.feeding["food_id"]:
            self.canvas.delete(self.feeding["food_id"])
        self.feeding["food_id"] = None
        self.feeding["active"] = False
        self.feeding["cooldown_until"] = time.time() + 1.2
        self.stats["hunger"] = min(100, self.stats["hunger"] + 25)
        self.stats["clean"]  = max(0,  self.stats["clean"]  - 3)
        self.set_face("happy"); self.update_bars(); self.save()

    # ===== あそぶ（積み木）演出 =====
    def start_playing(self):
        x = self.SCREEN_LEFT + self.SCREEN_W//2
        y = self.SCREEN_TOP  + self.SCREEN_H - int(self.SCREEN_H*0.12)
        if self.imgs.get("block"):
            obj_id = self.canvas.create_image(x, y, image=self.imgs["block"])
        else:
            obj_id = self.canvas.create_text(x, y, text="🧩", font=("Arial", 32))
        self.playing.update({"active": True, "step": 0, "obj_id": obj_id, "next_tick": time.time() + 0.4})
        self.set_face("happy")
        self.toast("つみきであそんでるよ🧩", ms=700)

    def tick_playing(self):
        if not self.playing["active"]:
            return
        now = time.time()
        if now < self.playing["next_tick"]:
            return
        self.playing["step"] += 1
        self.playing["next_tick"] = now + 0.4
        # ちょっと大きめに揺らす
        dy = -6 if (self.playing["step"] % 2 == 1) else 6
        self.canvas.move(self.char_id, 0, dy)
        if self.playing["step"] >= 3:
            self.end_playing()

    def end_playing(self):
        if self.playing["obj_id"]:
            self.canvas.delete(self.playing["obj_id"])
        self.playing["obj_id"] = None
        self.playing["active"] = False
        # BUG修正：以前 min(10, self.stats["fun"]+25) になっていた→100が正しい
        self.stats["fun"] = min(100, self.stats["fun"] + 25)
        self.set_face("happy"); self.update_bars(); self.save()

    # ===== うんち =====
    def maybe_make_poop(self):
        p = 0.02 + (1 - self.stats["clean"]/100) * 0.05
        if random() < p and len(self.poops) < 3 and self.imgs["poop"] is not None:
            x = self.SCREEN_LEFT + 20 + int(random()*(self.SCREEN_W-40))
            y = self.SCREEN_TOP  + 20 + int(random()*(self.SCREEN_H-40))
            po = self.canvas.create_image(x, y, image=self.imgs["poop"])
            self.poops.append(po)

    def clean_poop(self, po_item):
        if po_item in self.poops:
            self.canvas.delete(po_item)
            self.poops.remove(po_item)
            self.stats["clean"] = min(100, self.stats["clean"] + 5)
            self.update_bars(); self.save()
            self.toast("おそうじ完了🧻", ms=700)

    # ===== 表情 =====
    def set_face(self, name):
        self.canvas.itemconfig(self.char_id, image=self.imgs.get(name, self.imgs["happy"]))

    # ===== メインループ =====
    def tick(self):
        # 各演出の進行
        self.tick_feeding()
        self.tick_playing()

        # 5秒ごとにステータス減衰
        now = time.time()
        dt = max(0.0, now - self.stats["last_tick"])
        if dt >= 5.0:
            self.stats["last_tick"] = now
            self.stats["lifetime_sec"] += dt
            self.stats["hunger"] = max(0, self.stats["hunger"] - 2)
            self.stats["fun"]    = max(0, self.stats["fun"]    - 1)
            self.stats["clean"]  = max(0, self.stats["clean"]  - 1)
            self.update_bars()
            self.maybe_make_poop()

            # 表情ロジック
            if self.stats["hunger"] < 35:
                self.set_face("hungry")
            elif self.stats["fun"] < 35:
                self.set_face("sleepy")
            elif self.stats["clean"] < 35 or self.poops:
                self.set_face("sleepy")
            else:
                self.set_face("happy")
            self.save()

        self.root.after(200, self.tick)

    # ===== セーブ/ロード =====
    def save(self):
        try:
            with open(SAVE_FILE, "w", encoding="utf-8") as f:
                json.dump({"stats": self.stats}, f)
        except Exception:
            pass

    def load(self):
        if not os.path.exists(SAVE_FILE):
            return
        try:
            with open(SAVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.stats.update(data.get("stats", {}))
            self.update_bars()
        except Exception:
            pass


if __name__ == "__main__":
    root = Tk()
    app = TamaApp(root)
    root.mainloop()
