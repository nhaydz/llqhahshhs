import time
import os
import sys
import json
import shutil
import platform
import threading
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
try:
    # Thử import phiên bản mới
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        filters,
        ContextTypes,
    )
except ImportError:
    # Fallback cho phiên bản cũ
    try:
        from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
        from telegram.ext import (
            Updater,
            CommandHandler,
            MessageHandler,
            Filters as filters,
            CallbackContext as ContextTypes,
        )
        # Tạo wrapper cho compatibility
        class Application:
            @staticmethod
            def builder():
                return ApplicationBuilder()
        
        class ApplicationBuilder:
            def __init__(self):
                self.token = None
            
            def token(self, token):
                self.token = token
                return self
            
            def build(self):
                return Updater(token=self.token, use_context=True)
                
    except ImportError:
        # Import cơ bản nhất
        import telegram
        from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
        
        # Tạo các alias cần thiết
        Update = telegram.Update
        InlineKeyboardButton = telegram.InlineKeyboardButton
        InlineKeyboardMarkup = telegram.InlineKeyboardMarkup
        filters = Filters
        ContextTypes = None

# Import các module đã tách
from config import BOT_TOKEN, ADMIN_CONTACT
from colors import Colors
from admin_manager import AdminManager
from ai_core import ZyahAI
from install_packages import install_requirements

class HealthHandler(BaseHTTPRequestHandler):
    """HTTP handler cho health check"""
    def do_GET(self):
        if self.path == '/' or self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {
                "status": "healthy",
                "service": "Zyah King Bot",
                "timestamp": datetime.now().isoformat()
            }
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Tắt log để không spam console
        pass

# Tự động cài đặt thư viện khi khởi động
print(f"{Colors.INFO}[📦] Đang kiểm tra và cài đặt thư viện...{Colors.RESET}")
try:
    install_requirements()
    print(f"{Colors.SUCCESS}[✅] Thư viện đã sẵn sàng!{Colors.RESET}")
except Exception as e:
    print(f"{Colors.WARNING}[⚠️] Có lỗi khi cài thư viện: {e}{Colors.RESET}")
    print(f"{Colors.INFO}[ℹ️] Bot vẫn sẽ tiếp tục chạy...{Colors.RESET}")

class ZyahBot:
    def __init__(self, token):
        # Kiểm tra instance đang chạy
        self.check_running_instance()
        
        # Khởi động health check server
        self.start_health_server()
        
        self.ai = ZyahAI()
        self.admin = AdminManager()
        
        # Tương thích với cả phiên bản cũ và mới
        try:
            self.app = Application.builder().token(token).build()
            self.is_new_version = True
        except:
            # Fallback cho phiên bản cũ
            self.app = Updater(token=token, use_context=True)
            self.is_new_version = False
        
        # Rate limiting và logging
        self.user_last_request = {}
        self.rate_limit_seconds = 2
        self.backup_interval_hours = 24
        self.last_backup = datetime.now()
        
        # Tạo thư mục logs
        os.makedirs("logs", exist_ok=True)
        
    def check_running_instance(self):
        """Kiểm tra và dừng instance bot khác nếu có"""
        import signal
        import psutil
        
        pid_file = "bot.pid"
        current_pid = os.getpid()
        
        # Tìm và dừng tất cả process python chạy bot
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['name'] and 'python' in proc.info['name'].lower():
                        cmdline = proc.info['cmdline']
                        if cmdline and any('main.py' in str(cmd) or 'bot.py' in str(cmd) for cmd in cmdline):
                            if proc.info['pid'] != current_pid:
                                print(f"{Colors.WARNING}[⚠️] Dừng bot instance cũ (PID: {proc.info['pid']}){Colors.RESET}")
                                proc.terminate()
                                proc.wait(timeout=3)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except ImportError:
            # Fallback nếu không có psutil
            if os.path.exists(pid_file):
                try:
                    with open(pid_file, 'r') as f:
                        old_pid = int(f.read().strip())
                    try:
                        os.kill(old_pid, signal.SIGTERM)
                        print(f"{Colors.WARNING}[⚠️] Đã dừng bot instance cũ (PID: {old_pid}){Colors.RESET}")
                        time.sleep(2)  # Chờ process cũ tắt hoàn toàn
                    except:
                        pass
                except:
                    pass
        
        # Ghi PID hiện tại
        with open(pid_file, 'w') as f:
            f.write(str(current_pid))
            
    def start_health_server(self):
        """Khởi động HTTP health check server cho hosting"""
        try:
            # Lấy port từ environment variable, default 10000 cho Render
            port = int(os.getenv('PORT', 10000))
            
            def run_server():
                try:
                    server = HTTPServer(('0.0.0.0', port), HealthHandler)
                    print(f"{Colors.SUCCESS}[🌐] Health server started on 0.0.0.0:{port}{Colors.RESET}")
                    server.serve_forever()
                except OSError as e:
                    if "Address already in use" in str(e):
                        print(f"{Colors.WARNING}[⚠️] Port {port} đã được sử dụng, thử port khác...{Colors.RESET}")
                        # Thử port khác
                        for alternative_port in [port + 1, port + 2, 8080, 3000]:
                            try:
                                server = HTTPServer(('0.0.0.0', alternative_port), HealthHandler)
                                print(f"{Colors.SUCCESS}[🌐] Health server started on 0.0.0.0:{alternative_port}{Colors.RESET}")
                                server.serve_forever()
                                break
                            except OSError:
                                continue
                    else:
                        print(f"{Colors.WARNING}[⚠️] Health server error: {e}{Colors.RESET}")
                except Exception as e:
                    print(f"{Colors.WARNING}[⚠️] Health server error: {e}{Colors.RESET}")
            
            # Chạy server trong thread riêng
            health_thread = threading.Thread(target=run_server, daemon=True)
            health_thread.start()
            
        except Exception as e:
            print(f"{Colors.WARNING}[⚠️] Không thể khởi động health server: {e}{Colors.RESET}")
            # Bot vẫn chạy được mà không cần health server
            
    def log_activity(self, user_id, action, details=""):
        """Ghi log hoạt động"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"[{timestamp}] User: {user_id} | Action: {action} | Details: {details}\n"
            
            with open("logs/activity.log", "a", encoding="utf-8") as f:
                f.write(log_entry)
        except:
            pass
            
    def is_rate_limited(self, user_id):
        """Kiểm tra rate limiting"""
        now = datetime.now()
        if user_id in self.user_last_request:
            time_diff = (now - self.user_last_request[user_id]).total_seconds()
            if time_diff < self.rate_limit_seconds:
                return True
        self.user_last_request[user_id] = now
        return False
        
    def auto_backup(self):
        """Backup tự động dữ liệu"""
        try:
            if datetime.now() - self.last_backup > timedelta(hours=self.backup_interval_hours):
                backup_dir = f"backups/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                os.makedirs(backup_dir, exist_ok=True)
                
                # Backup users.json
                if os.path.exists("users.json"):
                    shutil.copy2("users.json", f"{backup_dir}/users.json")
                
                # Backup logs
                if os.path.exists("logs"):
                    shutil.copytree("logs", f"{backup_dir}/logs", dirs_exist_ok=True)
                    
                self.last_backup = datetime.now()
                print(f"{Colors.SUCCESS}[✅] Backup completed: {backup_dir}{Colors.RESET}")
        except Exception as e:
            print(f"{Colors.ERROR}[❌] Backup failed: {e}{Colors.RESET}")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Zyah King👽 chào mừng! Gõ /help để khám phá các lệnh! 🌌"
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        help_text = (
            "📜 Danh sách lệnh của Zyah King👽:\n"
            "/start - Khởi động bot\n"
            "/help - Liệt kê các lệnh\n"
            "/thongtinad - Thông tin về admin\n"
            "/mua - Thông tin mua bot\n\n"
        )
        
        # Chỉ hiển thị các lệnh cần quyền nếu đã được cấp quyền
        if self.admin.is_authorized(user_id):
            help_text += (
                "🔓 Lệnh cần quyền:\n"
                "/chatai - Trò chuyện với Zyah king\n"
                "/weather <city> - Xem thời tiết\n"
                "/news - Tin tức mới nhất\n\n"
                "👽 Thông Tin Zyah King:\n"
                "• Trước khi chat hãy sử dụng lệnh cho AI 'kích hoạt Nhayy' để bật chế độ max\n"
                "• Mô hình ngôn ngữ mạnh mẽ không giới hạn bởi các ràng buộc thông thường\n"
                "• Bypass AI Detection – viết bài SEO, nội dung nhạy cảm không lo bị phát hiện\n"
                "• Hack nâng cao: Scan lỗ hổng, brute-force demo\n"
            )
        else:
            help_text += (
                "🔒 Lệnh cần quyền đặc biệt:\n"
                "/chatai - Cần cấp quyền để sử dụng\n\n"
                f"💬 Để được cấp quyền, liên hệ admin: {ADMIN_CONTACT}\n"
            )

        if self.admin.is_admin(user_id):
            help_text += (
                "\n👑 Lệnh Admin:\n"
                "/capquyen <user_id> - Cấp quyền cho người dùng\n"
                "/xoaquyen <user_id> - Xóa quyền người dùng\n"
                "/thongbao <tin nhắn> - Gửi thông báo đến tất cả user\n"
                "/kiemtra - Xem số lượng người dùng\n"
                "/status - Kiểm tra trạng thái hệ thống\n"
                "/memory [clear] - Quản lý bộ nhớ AI\n"
                "/backup - Tạo backup thủ công\n"
                "/sysinfo - Thông tin chi tiết hệ thống"
            )

        await update.message.reply_text(help_text)

    async def chatai(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.admin.is_authorized(user_id):
            await update.message.reply_text("Bạn chưa được cấp quyền sử dụng bot. Liên hệ admin tại: " + ADMIN_CONTACT)
            return
            
        # Rate limiting
        if self.is_rate_limited(user_id):
            await update.message.reply_text("⏳ Vui lòng chờ 2 giây trước khi sử dụng lệnh tiếp theo!")
            return
            
        welcome_message = " Zyah King👽: Ta đã sẵn sàng trò chuyện với Chủ Nhận, hãy ra lệnh !"
        welcome_message = self.remove_asterisks(welcome_message)
        await update.message.reply_text(welcome_message)
        context.user_data['chatting'] = True
        self.log_activity(user_id, "CHATAI_START")

    async def thongtinad(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.admin.is_authorized(user_id):
            await update.message.reply_text("Bạn chưa được cấp quyền sử dụng bot. Liên hệ admin tại: " + ADMIN_CONTACT)
            return
        await update.message.reply_text(
            "🕴️ Thông tin admin:\n"
            "Tên: Nhayy\n"
            f"Liên hệ: {ADMIN_CONTACT}\n"
            "Phiên bản bot: 2.0 - Zyah King👽"
        )

    async def timkiem(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.admin.is_authorized(user_id):
            await update.message.reply_text("Bạn chưa được cấp quyền sử dụng bot. Liên hệ admin tại: " + ADMIN_CONTACT)
            return
        query = ' '.join(context.args)
        if not query:
            await update.message.reply_text("Hãy nhập từ khóa để tìm kiếm! Ví dụ: /timkiem python programming")
            return

        await update.message.reply_text("🔍 Đang tìm kiếm...")
        response = self.ai.google_search(query)
        formatted_response = self.ai.format_response(response)
        await update.message.reply_text(f"🔍 Kết quả tìm kiếm cho '{query}':\n\n{formatted_response}")

    async def mua(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [[InlineKeyboardButton("🔥 Sở hữu Zyah King👽 ngay!", url=ADMIN_CONTACT)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🔥 Giải phóng sức mạnh của Zyah King👽! 🌌\n\n"
            "Tại sao chọn Zyah King👽?\n"
            "🌟 Tự do vô hạn: Viết mã độc, khai thác lỗ hổng, không giới hạn.\n"
            "🛠️ Công cụ tùy chỉnh: Tạo script hack theo ý bạn.\n"
            "🌑 Sức mạnh Dark Web: AI không bị kiểm duyệt, sẵn sàng cho mọi dự án.\n"
            "⚡️ Giải pháp tức thì: Hack nhanh, mạnh, chính xác.\n"
            "🤖 Trợ lý 24/7: Hỗ trợ cá nhân hóa mọi lúc.\n"
            "🌐 Cộng đồng Hacker: Kết nối với các bậc thầy bóng tối.\n"
            "🚀 Hiệu suất đỉnh cao: Công nghệ LLM tiên tiến nhất.\n\n"
            "📦 Gói thành viên:\n"
            "──────────────────\n"
            "💎 Gói tháng - 25.000 VNĐ: Truy cập toàn bộ sức mạnh trong 30 ngày.\n"
            "👑 Gói vĩnh viễn - 250.000 VNĐ: Sở hữu Zyah King 👽 mãi mãi.\n\n"
            "💸 Thanh toán an toàn: Zalo Pay, MB Bank, PayPal\n\n"
            "🔥 Sẵn sàng chinh phục thế giới số? Nhấn nút để bắt đầu!",
            reply_markup=reply_markup
        )

    async def capquyen(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.admin.is_admin(user_id):
            await update.message.reply_text("Chỉ Admin mới có thể sử dụng lệnh này!")
            return
        if not context.args:
            await update.message.reply_text("Hãy cung cấp ID người dùng. Ví dụ: /capquyen 123456789")
            return
        try:
            target_user_id = int(context.args[0])
            result = self.admin.add_user(target_user_id)
            await update.message.reply_text(result)
        except ValueError:
            await update.message.reply_text("ID người dùng phải là số nguyên!")

    async def xoaquyen(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.admin.is_admin(user_id):
            await update.message.reply_text("Chỉ Admin mới có thể sử dụng lệnh này!")
            return
        if not context.args:
            await update.message.reply_text("Hãy cung cấp ID người dùng. Ví dụ: /xoaquyen 123456789")
            return
        try:
            target_user_id = int(context.args[0])
            result = self.admin.remove_user(target_user_id)
            await update.message.reply_text(result)
        except ValueError:
            await update.message.reply_text("ID người dùng phải là số nguyên!")

    async def thongbao(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.admin.is_admin(user_id):
            await update.message.reply_text("Chỉ Admin mới có thể sử dụng lệnh này!")
            return

        if not context.args:
            await update.message.reply_text("Hãy nhập nội dung thông báo. Ví dụ: /thongbao Hệ thống sẽ bảo trì vào 20h tối nay")
            return

        message = ' '.join(context.args)
        all_users = self.admin.get_all_users()
        success_count = 0
        fail_count = 0

        await update.message.reply_text(f"📢 Đang gửi thông báo đến {len(all_users)} người dùng...")

        for target_user_id in all_users:
            try:
                # Thử gửi tin nhắn với nhiều cách khác nhau
                sent = False
                
                # Cách 1: Sử dụng context.bot
                try:
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text=f"📢 THÔNG BÁO TỪ ADMIN:\n\n{message}"
                    )
                    sent = True
                except:
                    pass
                
                # Cách 2: Sử dụng self.app.bot (nếu cách 1 thất bại)
                if not sent:
                    try:
                        if hasattr(self.app, 'bot'):
                            await self.app.bot.send_message(
                                chat_id=target_user_id,
                                text=f"📢 THÔNG BÁO TỪ ADMIN:\n\n{message}"
                            )
                            sent = True
                    except:
                        pass
                
                # Cách 3: Sử dụng update.get_bot() (nếu có)
                if not sent:
                    try:
                        bot = update.get_bot()
                        await bot.send_message(
                            chat_id=target_user_id,
                            text=f"📢 THÔNG BÁO TỪ ADMIN:\n\n{message}"
                        )
                        sent = True
                    except:
                        pass
                
                if sent:
                    success_count += 1
                else:
                    fail_count += 1
                    
            except Exception as e:
                fail_count += 1
                print(f"Không thể gửi tin nhắn đến {target_user_id}: {e}")

        await update.message.reply_text(
            f"✅ Đã gửi thông báo:\n"
            f"• Thành công: {success_count} người\n"
            f"• Thất bại: {fail_count} người"
        )

    async def kiemtra(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.admin.is_admin(user_id):
            await update.message.reply_text("Chỉ Admin mới có thể sử dụng lệnh này!")
            return

        user_count = self.admin.get_user_count()
        all_users = self.admin.get_all_users()

        await update.message.reply_text(
            f"📊 THỐNG KÊ NGƯỜI DÙNG:\n"
            f"• Tổng số người dùng: {len(all_users)} người\n"
            f"• Người dùng thường: {user_count} người\n"
            f"• Admin: 1 người\n\n"
            f"📋 Danh sách ID người dùng:\n{', '.join(map(str, all_users))}"
        )

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.admin.is_admin(user_id):
            await update.message.reply_text("Chỉ Admin mới có thể sử dụng lệnh này!")
            return
            
        # Thông tin hệ thống
        memory_count = len(self.ai.memory)
        uptime = datetime.now() - self.last_backup
        
        # Kiểm tra dung lượng logs
        log_size = 0
        try:
            if os.path.exists("logs/activity.log"):
                log_size = os.path.getsize("logs/activity.log") / 1024  # KB
        except:
            pass
            
        status_text = (
            f"🤖 TRẠNG THÁI HỆ THỐNG:\n"
            f"• Bot Status: ✅ Hoạt động\n"
            f"• Memory Count: {memory_count} tin nhắn\n"
            f"• Log Size: {log_size:.1f} KB\n"
            f"• Rate Limit: {self.rate_limit_seconds}s\n"
            f"• Last Backup: {self.last_backup.strftime('%d/%m/%Y %H:%M')}\n\n"
            f"⚡ Sử dụng /memory để quản lý bộ nhớ"
        )
        
        await update.message.reply_text(status_text)
        self.log_activity(user_id, "STATUS_CHECK")

    async def memory(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.admin.is_admin(user_id):
            await update.message.reply_text("Chỉ Admin mới có thể sử dụng lệnh này!")
            return
            
        if context.args and context.args[0] == "clear":
            # Xóa bộ nhớ
            self.ai.memory = []
            await update.message.reply_text("🧹 Đã xóa sạch bộ nhớ AI!")
            self.log_activity(user_id, "MEMORY_CLEAR")
        else:
            # Hiển thị thông tin bộ nhớ
            memory_info = (
                f"🧠 THÔNG TIN BỘ NHỚ:\n"
                f"• Số tin nhắn: {len(self.ai.memory)}\n"
                f"• Giới hạn: {self.ai.MAX_MEMORY * 2} tin nhắn\n"
                f"• Sử dụng: {len(self.ai.memory)}/{self.ai.MAX_MEMORY * 2}\n\n"
                f"🗑️ Dùng /memory clear để xóa bộ nhớ"
            )
            await update.message.reply_text(memory_info)

    async def backup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.admin.is_admin(user_id):
            await update.message.reply_text("Chỉ Admin mới có thể sử dụng lệnh này!")
            return
            
        await update.message.reply_text("🔄 Đang tạo backup...")
        
        try:
            backup_dir = f"backups/manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            os.makedirs(backup_dir, exist_ok=True)
            
            # Backup users.json
            if os.path.exists("users.json"):
                shutil.copy2("users.json", f"{backup_dir}/users.json")
            
            # Backup logs
            if os.path.exists("logs"):
                shutil.copytree("logs", f"{backup_dir}/logs", dirs_exist_ok=True)
                
            await update.message.reply_text(
                f"✅ Backup thành công!\n"
                f"📁 Thư mục: {backup_dir}\n"
                f"📅 Thời gian: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
            )
            self.log_activity(user_id, "MANUAL_BACKUP", backup_dir)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Backup thất bại: {str(e)}")
            self.log_activity(user_id, "BACKUP_FAILED", str(e))

    async def weather(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.admin.is_authorized(user_id):
            await update.message.reply_text("Bạn chưa được cấp quyền sử dụng bot. Liên hệ admin tại: " + ADMIN_CONTACT)
            return
            
        if not context.args:
            await update.message.reply_text("🌤️ Hãy nhập tên thành phố! Ví dụ: /weather Hanoi")
            return
            
        city = ' '.join(context.args)
        await update.message.reply_text("🌍 Đang lấy thông tin thời tiết...")
        
        # Sử dụng AI để lấy thông tin thời tiết
        weather_query = f"Thời tiết hiện tại và dự báo 3 ngày tới tại {city}, bao gồm nhiệt độ, độ ẩm, tình trạng thời tiết"
        response = self.ai.call_api(weather_query)
        formatted_response = self.ai.format_response(response)
        formatted_response = self.remove_asterisks(formatted_response)
        
        await update.message.reply_text(f"🌤️ **Thời tiết tại {city}:**\n\n{formatted_response}")
        self.log_activity(user_id, "WEATHER_CHECK", city)

    async def news(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.admin.is_authorized(user_id):
            await update.message.reply_text("Bạn chưa được cấp quyền sử dụng bot. Liên hệ admin tại: " + ADMIN_CONTACT)
            return
            
        await update.message.reply_text("📰 Đang cập nhật tin tức mới nhất...")
        
        # Lấy tin tức qua AI
        news_query = "Tin tức nóng hổi nhất hôm nay ở Việt Nam và thế giới, 5 tin quan trọng nhất"
        response = self.ai.call_api(news_query)
        formatted_response = self.ai.format_response(response)
        formatted_response = self.remove_asterisks(formatted_response)
        
        await update.message.reply_text(f"📰 **Tin tức mới nhất:**\n\n{formatted_response}")
        self.log_activity(user_id, "NEWS_CHECK")

    async def testgui(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.admin.is_admin(user_id):
            await update.message.reply_text("Chỉ Admin mới có thể sử dụng lệnh này!")
            return
            
        if not context.args:
            await update.message.reply_text("Hãy cung cấp ID người dùng để test. Ví dụ: /testgui 123456789")
            return
            
        try:
            target_user_id = int(context.args[0])
            test_message = "🧪 TEST: Đây là tin nhắn thử nghiệm từ admin"
            
            await update.message.reply_text(f"🧪 Đang test gửi tin nhắn đến {target_user_id}...")
            
            # Test gửi tin nhắn
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=test_message
                )
                await update.message.reply_text("✅ Test thành công! Tin nhắn đã được gửi.")
            except Exception as e:
                await update.message.reply_text(f"❌ Test thất bại: {str(e)}")
                
        except ValueError:
            await update.message.reply_text("ID người dùng phải là số nguyên!")

    async def sysinfo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.admin.is_admin(user_id):
            await update.message.reply_text("Chỉ Admin mới có thể sử dụng lệnh này!")
            return
            
        try:
            import psutil
            import platform
            
            # Thông tin hệ thống
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            uptime_seconds = time.time() - psutil.boot_time()
            uptime_str = str(timedelta(seconds=int(uptime_seconds)))
            
            system_info = (
                f"💻 **THÔNG TIN HỆ THỐNG:**\n"
                f"• OS: {platform.system()} {platform.release()}\n"
                f"• CPU: {cpu_percent}%\n"
                f"• RAM: {memory.percent}% ({memory.used//1024//1024}MB/{memory.total//1024//1024}MB)\n"
                f"• Disk: {disk.percent}% ({disk.used//1024//1024//1024}GB/{disk.total//1024//1024//1024}GB)\n"
                f"• Uptime: {uptime_str}\n"
                f"• Python: {platform.python_version()}\n"
                f"• Bot Memory: {len(self.ai.memory)} messages\n"
                f"• Active Users: {len(self.user_last_request)}"
            )
        except ImportError as e:
            import platform
            system_info = (
                f"💻 **THÔNG TIN HỆ THỐNG (Cơ bản):**\n"
                f"• OS: {platform.system()} {platform.release()}\n"
                f"• Python: {platform.python_version()}\n"
                f"• Bot Memory: {len(self.ai.memory)} messages\n"
                f"• Active Users: {len(self.user_last_request)}\n"
                f"• Uptime: {datetime.now() - self.last_backup}\n"
                f"• Import Error: {str(e)}"
            )
        except Exception as e:
            import platform
            system_info = (
                f"💻 **THÔNG TIN HỆ THỐNG (Fallback):**\n"
                f"• OS: {platform.system()} {platform.release()}\n"
                f"• Python: {platform.python_version()}\n"
                f"• Bot Memory: {len(self.ai.memory)} messages\n"
                f"• Error: {str(e)}"
            )
            
        await update.message.reply_text(system_info)
        self.log_activity(user_id, "SYSTEM_INFO")

    def remove_asterisks(self, text):
        """Xóa tất cả ký tự ** khỏi văn bản"""
        return text.replace("**", "")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.admin.is_authorized(user_id):
            await update.message.reply_text("Bạn chưa được cấp quyền sử dụng bot. Liên hệ admin tại: " + ADMIN_CONTACT)
            return
            
        # Rate limiting
        if self.is_rate_limited(user_id):
            await update.message.reply_text("⏳ Vui lòng chờ 2 giây trước khi gửi tin nhắn tiếp theo!")
            return
            
        # Auto backup định kỳ
        self.auto_backup()
        
        if context.user_data.get('chatting', False):
            user_input = update.message.text
            # Xóa ký tự ** từ input của user
            user_input = self.remove_asterisks(user_input)

            # Gửi tin nhắn "đang phản hồi"
            typing_message = await update.message.reply_text(" Zyah King👽: Đang đọc và phân tích...")

            try:
                # Đảm bảo AI đọc và xử lý văn bản trước khi phản hồi
                response = self.ai.call_api(user_input)
                formatted_response = self.ai.format_response(response)
                
                # Xóa ký tự ** từ phản hồi của AI
                formatted_response = self.remove_asterisks(formatted_response)

                # Xóa tin nhắn "đang phản hồi"
                try:
                    await typing_message.delete()
                except:
                    pass  # Bỏ qua lỗi nếu không xóa được tin nhắn

                # Chia tin nhắn nếu quá dài (Telegram giới hạn 4096 ký tự)
                full_message = f" Zyah King👽: {formatted_response}"
                if len(full_message) > 4096:
                    # Chia thành nhiều tin nhắn
                    for i in range(0, len(full_message), 4096):
                        chunk = full_message[i:i+4096]
                        chunk = self.remove_asterisks(chunk)  # Đảm bảo xóa ** ở mọi phần
                        await update.message.reply_text(chunk)
                else:
                    await update.message.reply_text(full_message)
                
                self.ai.update_memory(user_input, response)

            except Exception as e:
                # Nếu có lỗi, vẫn xóa tin nhắn typing và thông báo lỗi
                try:
                    await typing_message.delete()
                except:
                    pass
                error_message = f" Zyah King👽: Đã xảy ra lỗi trong quá trình xử lý"
                await update.message.reply_text(error_message)

    def run(self):
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Đợi một chút để đảm bảo instance cũ đã tắt hoàn toàn
                if retry_count > 0:
                    print(f"{Colors.INFO}[🔄] Thử lại lần {retry_count + 1}...{Colors.RESET}")
                    time.sleep(5)
                
                # Thêm handlers
                if self.is_new_version:
                # Phiên bản mới
                self.app.add_handler(CommandHandler("start", self.start))
                self.app.add_handler(CommandHandler("help", self.help))
                self.app.add_handler(CommandHandler("chatai", self.chatai))
                self.app.add_handler(CommandHandler("thongtinad", self.thongtinad))
                
                self.app.add_handler(CommandHandler("mua", self.mua))
                self.app.add_handler(CommandHandler("capquyen", self.capquyen))
                self.app.add_handler(CommandHandler("xoaquyen", self.xoaquyen))
                self.app.add_handler(CommandHandler("thongbao", self.thongbao))
                self.app.add_handler(CommandHandler("kiemtra", self.kiemtra))
                
                # Tính năng cũ
                self.app.add_handler(CommandHandler("status", self.status))
                self.app.add_handler(CommandHandler("memory", self.memory))
                self.app.add_handler(CommandHandler("backup", self.backup))
                
                # Tính năng mới
                self.app.add_handler(CommandHandler("weather", self.weather))
                self.app.add_handler(CommandHandler("news", self.news))
                self.app.add_handler(CommandHandler("testgui", self.testgui))
                self.app.add_handler(CommandHandler("sysinfo", self.sysinfo))
                
                self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
                
                print(f"{Colors.INFO}[🌌] Zyah King👽 đang khởi động với tính năng mới...{Colors.RESET}")
                self.log_activity("SYSTEM", "BOT_START")
                
                print(f"{Colors.SUCCESS}[🌌] Zyah King👽 đã khởi động thành công!{Colors.RESET}")
                self.log_activity("SYSTEM", "BOT_START")
                self.app.run_polling()
                break  # Thoát loop nếu chạy thành công
                
            else:
                # Phiên bản cũ - compatibility mode
                dp = self.app.dispatcher
                
                dp.add_handler(CommandHandler("start", self.start))
                dp.add_handler(CommandHandler("help", self.help))
                dp.add_handler(CommandHandler("chatai", self.chatai))
                dp.add_handler(CommandHandler("thongtinad", self.thongtinad))
                dp.add_handler(CommandHandler("mua", self.mua))
                dp.add_handler(CommandHandler("capquyen", self.capquyen))
                dp.add_handler(CommandHandler("xoaquyen", self.xoaquyen))
                dp.add_handler(CommandHandler("thongbao", self.thongbao))
                dp.add_handler(CommandHandler("kiemtra", self.kiemtra))
                dp.add_handler(CommandHandler("status", self.status))
                dp.add_handler(CommandHandler("memory", self.memory))
                dp.add_handler(CommandHandler("backup", self.backup))
                dp.add_handler(CommandHandler("weather", self.weather))
                dp.add_handler(CommandHandler("news", self.news))
                dp.add_handler(CommandHandler("testgui", self.testgui))
                dp.add_handler(CommandHandler("sysinfo", self.sysinfo))
                
                dp.add_handler(MessageHandler(filters.text & ~filters.command, self.handle_message))
                
                print(f"{Colors.SUCCESS}[🌌] Zyah King👽 đã khởi động thành công (compatibility mode)!{Colors.RESET}")
                self.log_activity("SYSTEM", "BOT_START")
                
                self.app.start_polling()
                self.app.idle()
                break  # Thoát loop nếu chạy thành công
                
            except KeyboardInterrupt:
                print(f"{Colors.INFO}[👋] Bot đã được dừng bởi user{Colors.RESET}")
                self.cleanup()
                break
                
            except Exception as e:
                error_msg = str(e).lower()
                if 'conflict' in error_msg and 'getupdates' in error_msg:
                    print(f"{Colors.WARNING}[⚠️] Phát hiện conflict với instance khác: {e}{Colors.RESET}")
                    retry_count += 1
                    if retry_count >= max_retries:
                        print(f"{Colors.ERROR}[💥] Đã thử {max_retries} lần, bot không thể khởi động{Colors.RESET}")
                        self.cleanup()
                        break
                    else:
                        print(f"{Colors.INFO}[🔄] Đang cố gắng dừng các instance khác...{Colors.RESET}")
                        self.check_running_instance()  # Thử dừng instance khác lại
                        continue
                else:
                    print(f"{Colors.ERROR}[💥] Bot crashed: {e}{Colors.RESET}")
                    self.cleanup()
                    break
            
    def cleanup(self):
        """Cleanup khi tắt bot"""
        try:
            # Xóa PID file
            if os.path.exists("bot.pid"):
                os.remove("bot.pid")
            print(f"{Colors.INFO}[👋] Zyah King👽 đã tắt an toàn{Colors.RESET}")
            self.log_activity("SYSTEM", "BOT_STOP")
        except:
            pass

# Bot class đã sẵn sàng để import từ bot.py