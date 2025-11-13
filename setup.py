#!/usr/bin/env python3
import os
import sys
import subprocess
import platform

VENV_NAME = "env"
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
VENV_DIR = os.path.join(SCRIPT_DIR, VENV_NAME)

def create_venv():
    if not os.path.isdir(VENV_DIR):
        print(f"Creating virtual environment '{VENV_NAME}'...")
        subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])
        print(f"Virtual environment '{VENV_NAME}' created.")
    else:
        print(f"Virtual environment '{VENV_NAME}' already exists.")

def get_pip_path():
    system = platform.system()
    return os.path.join(VENV_DIR, "Scripts" if system == "Windows" else "bin", "pip")

def get_python_path():
    system = platform.system()
    return os.path.join(VENV_DIR, "Scripts" if system == "Windows" else "bin", "python")

def install_requirements():
    system = platform.system()
    packages = ["Flask", "python-dotenv", "requests", "base58", "web3", "colorama", "pyinstaller"]

    if system != "Windows":
        packages.append("pywebview[qt]")
    else:
        packages.append("pywebview")

    pip_path = get_pip_path()
    print(f"Installing packages: {', '.join(packages)}")
    try:
        subprocess.check_call([pip_path, "install", "--upgrade", "pip"])
        subprocess.check_call([pip_path, "install", *packages])
        print("Packages installed successfully.")
    except subprocess.CalledProcessError:
        print("Failed to install some packages. On Windows, make sure you use 64-bit Python and have Visual C++ Build Tools installed.")
        sys.exit(1)

def build_executable():
    python_path = get_python_path()
    pyinstaller_cmd = [
        python_path, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--icon=gui/assets/exe.ico",
        "--add-data", "gui;gui",
        "--add-data", "utils;utils",
        "--add-data", ".env;.",
        "main.py"
    ]
    print("\nBuilding executable...")
    subprocess.check_call(pyinstaller_cmd)
    print("\nExecutable built successfully in the 'dist' folder!")

def main():
    create_venv()
    install_requirements()

    if len(sys.argv) > 1 and sys.argv[1].lower() == "build":
        build_executable()
    else:
        print("\nSetup complete. Activate your virtual environment with:")
        if platform.system() == "Windows":
            print(f"{VENV_DIR}\\Scripts\\activate")
        else:
            print(f"source {VENV_DIR}/bin/activate")
        print("\nThen run your project with:")
        print(f"{get_python_path()} main.py")

if __name__ == "__main__":
    main()
