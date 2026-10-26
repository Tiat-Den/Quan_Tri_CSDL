"""
Script khởi động nhanh ứng dụng Streamlit Text-to-SQL CSDL Linh Kiện.
"""
import os
import sys
import subprocess


def main():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    web_app_path = os.path.join(current_dir, "web_app.py")
    url = "http://localhost:8501"

    # Tắt thông báo hỏi email của Streamlit
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_CLIENT_TOOLBAR_MODE"] = "viewer"

    print("=" * 60)
    print("DANG KHOI DONG HE THONG TEXT-TO-SQL LINH KIEN MAY TINH...")
    print(f"File giao dien: {web_app_path}")
    print(f"Dia chi Website: {url}")
    print("Trinh duyet se tu dong mo 1 tab duy nhat...")
    print("Bam Ctrl + C trong Terminal de dung ung dung")
    print("=" * 60)

    cmd = [
        sys.executable, "-m", "streamlit", "run", web_app_path,
        "--server.port=8501",
        "--server.headless=false",
        "--browser.serverAddress=localhost"
    ]
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\nDa dung ung dung Streamlit.")


if __name__ == "__main__":
    main()
