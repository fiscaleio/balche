# balche/ui

## Overview

***balche*** is a graphical interface for a cryptocurrency wallet checker that retrieves balances across EVM chains, Solana, and Tron networks. It supports native tokens as well as common ERC20, SPL, and TRC20 tokens.  

## Requirements

Before you begin, ensure that you have the following installed:

- Python 3.12

## Steps to Run the Project

Follow these steps to build, set up, and run the project:

### 1. Clone the Repository

First, clone the repository by running the following command:

```bash
git clone https://github.com/fiscaleio/balche
```

### 2. Setup Environment and Install Dependencies

Run the following command to execute the setup script:

```bash
python setup.py
```

This will:  
- Create a virtual environment (`env`) if one doesn't exist.  
- Automatically install all required dependencies for either Windows or Linux.  

### 3. Build Executable (Optional)

If you want to compile an executable for Windows, run:

```bash
python setup.py build
```

This will use PyInstaller to create a single-file executable, Make sure you update the config inside utils/.env with your API keys

### 4. Launch the GUI Application

After the setup, run the main script to start the GUI application:

```bash
python main.py
```

You can then load wallet addresses from a file or paste them directly. The application will fetch balances for supported tokens and chains efficiently.  

### 5. Launch the CLI Version

If you prefer to use the command-line interface (CLI) version of the checker, run:

```bash
python utils/cli.py
```

CLI version supports the same functionality as the GUI.

## Author

[@FISCALEIO](https://t.me/fiscaleio)