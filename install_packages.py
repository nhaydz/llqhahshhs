import subprocess
import sys
import os

def install_requirements():
    """Tự động cài đặt các package từ requirements.txt"""
    packages_to_install = [
        "python-telegram-bot>=21.0.1",
        "requests>=2.32.3", 
        "colorama>=0.4.6",
        "pytz>=2025.2",
        "psutil>=5.9.0"
    ]
    try:
        # Kiểm tra xem requirements.txt có tồn tại không
        if not os.path.exists('requirements.txt'):
            print("❌ Không tìm thấy file requirements.txt")
            return False

        print("📦 Đang cài đặt các thư viện cần thiết...")

        # Cài đặt packages
        result = subprocess.run([
            sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'
        ], capture_output=True, text=True)

        if result.returncode == 0:
            print("✅ Đã cài đặt thành công tất cả thư viện!")
            return True
        else:
            print(f"❌ Lỗi khi cài đặt: {result.stderr}")
            return False

    except Exception as e:
        print(f"❌ Lỗi không mong muốn: {str(e)}")
        return False

if __name__ == "__main__":
    install_requirements()