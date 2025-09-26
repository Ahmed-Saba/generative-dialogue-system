# Setting Up and Using `uv` for Virtual Environment and Dependency Management

This guide explains how I installed and used [`uv`](https://github.com/astral-sh/uv) in this project to manage the Python virtual environment and install dependencies from `requirements.txt`.

## Table of Contents

- [What is `uv`](#what-is-uv)
- [Installation](#installation)
  - [On Windows (PowerShell)](#on-windows-powershell)
  - [On Linux / macOS](#on-linux--macos)
- [Project Setup Guide](#project-setup-guide)
  - [Create a Virtual Environment](#1-create-a-virtual-environment)
  - [Activate the Virtual Environment](#2-activate-the-virtual-environment)
  - [Initialize the Project Configuration](#3-initialize-the-project-configuration)
  - [Install Project Dependencies](#4-install-project-dependencies)
  - [Managing Dependencies with `uv`](#5-managing-dependencies-with-uv)

## What is `uv`?

`uv` is an ultra-fast Python package manager and virtual environment tool, built in Rust by the Astral team. It serves as a modern replacement for `pip`, `virtualenv`, and `pip-tools`.

## Installation

### On Windows (PowerShell)

To install `uv` , run the following PowerShell command:

```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

This downloaded the latest version and installed it to:

```powershell
C:\Users\<YourUsername>\.local\bin
```

Then, add the install directory to your `PATH` so you can run `uv` commands from anywhere:

1. Press **Win + X**, select **System**.

2. Click **Advanced system settings > Environment Variables**.

3. Under **User variables** or **System variables**, find the `Path` variable.

4. Click **Edit** and add:

    ```text
    C:\Users\<YourUsername>\.local\bin
    ```

5. Save everything, then restart your PowerShell or terminal.

### On Linux / macOS

To install `uv` on Linux or macOS, run the following command in your terminal:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

This will install `uv` into your local binary directory, typically:

```bash
~/.local/bin
```

## Project Setup Guide

### 1. Create a Virtual Environment

To create a virtual environment in the project directory, run:

```bash
uv venv
```

This will create a `.venv/` folder in the root of your project.

If you want to name the environment something else, you can specify it like this:

```bash
uv venv myenv
```

> **Note:** Make sure to add `.venv/` to your `.gitignore` file to avoid committing the virtual environment folder.

### 2. Activate the Virtual Environment

To activate the environment on PowerShell, run:

```powershell
.venv\Scripts\Activate.ps1
```

On Linux/macOS (Bash or Zsh), use:

```bash
source .venv/bin/activate
```

### 3. Initialize the Project Configuration

Run the following command to create a `pyproject.toml` file and set up basic project metadata:

```bash
uv init
```

This will prompt you to enter project details such as name, version, author, and license.

### 4. Install Project Dependencies

To install all the required libraries listed in your `requirements.txt` file and add them to your `pyproject.toml`, run:

```bash
uv add -r requirements.txt
```

This command installs the packages into your virtual environment and updates your project configuration accordingly.

### 5. Managing Dependencies with `uv`

Once your project is initialized, you can use `uv` to add, remove, or update dependencies directly in your `pyproject.toml`. This keeps your environment clean and your project configuration up to date.

| Action              | Command                                           |
| ------------------- | ------------------------------------------------- |
| Add a dependency    | `uv add <package>`                                |
| Add with version    | `uv add <package>==<version>`                     |
| Add multiple        | `uv add <pkg1> <pkg2>`                            |
| Remove a dependency | `uv remove <package>`                             |
| Update version      | `uv remove <pkg>` → `uv add <pkg>==<new-version>` |
