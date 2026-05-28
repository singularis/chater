# 🚀 Developer Onboarding Guide

Welcome to the team! This guide will get your machine fully set up to contribute to backend services, iOS/Android development, and to work with our Kubernetes cluster.

> This project is a **Python microservices backend** running on Kubernetes, with AI chat + food tracking features. Read the `README.md` for a full feature overview.

---

## 📋 Table of Contents
1. [Required Hardware](#required-hardware)
2. [Core Tools (Everyone)](#core-tools-everyone)
3. [Backend Development](#backend-development)
4. [Kubernetes & Cluster Access](#kubernetes--cluster-access)
5. [iOS Development](#ios-development)
6. [Android Development](#android-development)
7. [Cursor IDE Setup (AI-Powered)](#cursor-ide-setup-ai-powered)
8. [VPN Access (Tailscale)](#vpn-access-tailscale)
9. [First Day Checklist](#first-day-checklist)

---

## Required Hardware

| Platform | Minimum |
|---|---|
| **macOS** (for iOS) | Mac with Apple Silicon (M1/M2/M3) recommended, macOS 14+ |
| **Any OS** (backend only) | 16 GB RAM, 50 GB free disk |

> [!IMPORTANT]
> iOS development **requires a Mac**. Android and backend work can be done on Mac, Windows, or Linux.

---

## Core Tools (Everyone)

Install these first on any OS.

### 1. Homebrew (macOS/Linux package manager)
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 2. Fish Shell (terminal)
```bash
brew install fish
# Set as default shell
echo $(which fish) | sudo tee -a /etc/shells
chsh -s $(which fish)
```

Restart your terminal. Fish gives you autosuggestions, syntax highlighting, and smart completions out of the box — no config needed.

### 3. Git
```bash
brew install git

# Configure your identity
git config --global user.name "Your Name"
git config --global user.email "your@email.com"

# Set up SSH key for GitHub
ssh-keygen -t ed25519 -C "your@email.com"
cat ~/.ssh/id_ed25519.pub  # Paste this into GitHub → Settings → SSH Keys
```

### 4. GitHub CLI
```bash
brew install gh
gh auth login  # follow the prompts
```

---

## Backend Development

The backend is **Python (Flask/FastAPI)**. Each service lives in its own folder (e.g. `admin_service/`, `chater_ui/`, `eater/`).

### 1. Python (via pyenv — manage multiple versions)
```bash
brew install pyenv
echo 'pyenv init - | source' >> ~/.config/fish/config.fish
source ~/.config/fish/config.fish

pyenv install 3.12
pyenv global 3.12
```

### 2. Virtual Environments
Each service has its own dependencies. Always work inside a venv:
```bash
cd admin_service/
python -m venv venv
source venv/bin/activate.fish   # Fish syntax
pip install -r requirements.txt
```

### 3. Useful Python Tools
```bash
pip install ipython   # Better Python REPL
brew install httpie   # Easy HTTP requests for API testing (like curl but readable)
```

### 4. API Testing — Bruno
Bruno is a local-first Postman alternative. Download from [https://www.usebruno.com](https://www.usebruno.com).

---

## Kubernetes & Cluster Access

### 1. Install kubectl
```bash
brew install kubectl
```

### 2. Set up VPN (Tailscale) — see [VPN section below](#vpn-access-tailscale)

### 3. Get your kubeconfig
You'll receive a `kubeconfig.yaml` file from the team lead. Place it here:
```bash
mkdir -p ~/.kube
cp kubeconfig.yaml ~/.kube/config
```

### 4. k9s — Visual Kubernetes terminal UI (essential for juniors)
k9s is like a file manager, but for your Kubernetes cluster. Way easier than raw `kubectl` commands.
```bash
brew install k9s
k9s  # launches the UI
```

Key shortcuts inside k9s:
- `:pods` → view all pods
- `l` on a pod → view live logs
- `d` on a pod → describe
- `ctrl+c` → quit

### 5. Lens (optional GUI alternative to k9s)
If you prefer a full desktop app: [https://k8slens.dev](https://k8slens.dev)

### 6. Essential kubectl commands (cheatsheet)
```bash
# See what's running
kubectl get pods -n eater-dev
kubectl get pods -A           # all namespaces

# Read logs
kubectl logs <pod-name> -n eater-dev
kubectl logs <pod-name> -n eater-dev -f   # follow (live stream)

# Describe a pod (events, errors)
kubectl describe pod <pod-name> -n eater-dev

# Check ArgoCD app sync status
kubectl get applications -n argocd
```

---

## iOS Development

> Requires macOS.

### 1. Xcode
Install from the Mac App Store: [Xcode](https://apps.apple.com/us/app/xcode/id497799835)

After install, agree to the license and install components:
```bash
sudo xcodebuild -license accept
xcode-select --install
```

### 2. CocoaPods
Dependency manager for iOS projects:
```bash
brew install cocoapods
```

### 3. Swift Package Manager
Built into Xcode — no extra install needed. Use it for adding libraries directly inside Xcode via **File → Add Package Dependencies**.

### 4. Simulator
Bundled with Xcode. Open via:
```
Xcode → Window → Devices and Simulators
```

### 5. Fastlane (CI/CD for mobile — optional, for later)
```bash
brew install fastlane
```

---

## Android Development

### 1. Android Studio
Download from [https://developer.android.com/studio](https://developer.android.com/studio).

During setup, install:
- Android SDK
- Android Virtual Device (AVD) — for the emulator

### 2. Java (via SDKMAN)
```bash
curl -s "https://get.sdkman.io" | bash
sdk install java 17.0.9-tem
```

### 3. Kotlin
Built into Android Studio. No extra install needed.

### 4. ADB (Android Debug Bridge)
```bash
brew install android-platform-tools
adb devices   # check connected devices
```

### 5. Android Emulator Tips
- Use an **x86_64 / arm64** image (not x86 — it's faster)
- Enable **Hardware Acceleration** (HAXM on Intel, built-in on Apple Silicon)

---

## Cursor IDE Setup (AI-Powered)

Cursor is a VS Code fork with AI built in. It's what we use for **agentic development** — letting AI write, refactor, and explain code.

### 1. Install Cursor
Download from [https://www.cursor.com](https://www.cursor.com)

### 2. Essential Extensions to Install
Open Cursor → Extensions (`Cmd+Shift+X`) and install:

| Extension | Purpose |
|---|---|
| **Python** (Microsoft) | Python language support |
| **Pylance** | Python type checking |
| **YAML** (Red Hat) | Kubernetes/ArgoCD YAML editing |
| **Kubernetes** (Microsoft) | View cluster resources inside Cursor |
| **GitLens** | Visual git blame, history |
| **Docker** (Microsoft) | Manage containers |
| **Remote - SSH** | Edit files on remote servers |
| **Fish** | Fish shell syntax highlighting |

### 3. Cursor AI Tips for Beginners
- **`Cmd+K`** — inline AI edit (select code, press, describe the change)
- **`Cmd+L`** — open AI chat sidebar (ask questions about code)
- **`@file`** — reference a specific file in your AI prompt
- **`@codebase`** — search the whole repo with AI

> [!TIP]
> When you're stuck on a bug, paste the error into the Cursor chat (`Cmd+L`) and ask "What does this error mean and how do I fix it?" This is faster than Googling for beginners.

---

## VPN Access (Tailscale)

Tailscale is our VPN. Once connected, you can access the cluster directly — no need to be on the same physical network.

### 1. Install Tailscale
```bash
brew install tailscale
```
Or download the Mac app: [https://tailscale.com/download](https://tailscale.com/download)

### 2. Connect
You'll receive an **invite link** from the team lead. Click it to join the network. Log in with your Google or GitHub account.

### 3. Verify
Once connected, you should be able to reach the cluster:
```bash
curl https://192.168.0.10:6443 -k
# Should return a JSON response from the Kubernetes API
```

---

## First Day Checklist

Work through this list top to bottom. Check each item off as you go.

- `[ ]` Fish shell installed and set as default
- `[ ]` Git configured with your name/email + SSH key added to GitHub
- `[ ]` Cloned the repository: `git clone git@github.com:singularis/chater.git`
- `[ ]` Cursor IDE installed with all extensions
- `[ ]` Tailscale installed and joined the team network
- `[ ]` Kubeconfig received and placed in `~/.kube/config`
- `[ ]` Ran `k9s` and can see pods running
- `[ ]` Ran `kubectl logs` on a pod successfully
- `[ ]` Python + pyenv installed
- `[ ]` Ran a service locally inside a venv

- `[ ]` *(iOS only)* Xcode installed and a Simulator runs
- `[ ]` *(Android only)* Android Studio installed and an AVD runs

---

## Need Help?

1. **Check logs first** — `kubectl logs <pod> -n <namespace>`
2. **Check pod status** — `k9s` then `:pods`
3. **Ask in Slack/chat** with the full error message and what you already tried
4. **Use Cursor AI** — paste the error, ask for an explanation

> [!NOTE]
> It's completely normal to feel lost on day one. The tools listed above are industry standards — investing time to learn them pays off quickly.
