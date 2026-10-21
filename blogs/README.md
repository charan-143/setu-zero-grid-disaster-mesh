# Setu: Zero-Grid Disaster Mesh & Triage System — Technical Blog Series

This directory contains a complete, 4-part publication-ready technical blog series detailing the engineering, algorithms, physics, and mobile implementation of the **Setu Zero-Grid Disaster Mesh**.

---

## 📚 Blog Series Overview

| Part | Title | Focus & Breakthrough Innovations | Markdown File |
| :---: | :--- | :--- | :--- |
| **Part 1** | **The Pre-Installation Paradox & 4-Layer Mesh Architecture** | The physics of black-sky events, why Bridgefy/Meshtastic fail in sudden disasters, the 4-tier tactical blueprint, and the 120-byte bit-packed binary SOS packet specification. | [`01_zero_grid_disaster_mesh_architecture.md`](./01_zero_grid_disaster_mesh_architecture.md) |
| **Part 2** | **Physics Under Concrete: Cryo-Sleep & SAR-Tap Seismic Codec** | Extending 15% battery to 12.4 days under dark rubble (119.4x power reduction via lux/kinetic gating) and non-vocal seismic IMU coincidence fusion for victims with crushed chests. | [`02_cryo_sleep_and_sar_tap_seismic_codec.md`](./02_cryo_sleep_and_sar_tap_seismic_codec.md) |
| **Part 3** | **Mathematical Triage: 3D Acoustic Rubble Multilateration & Dynamic Trauma Decay** | Sub-surface 3D depth localization via GCC-PHAT ultrasonic TDoA ($Z = -2.5\text{m}$), and the ATLS/WHO dynamic physiological trauma decay and multi-team dispatch optimizer. | [`03_ultrasonic_tdoa_3d_depth_and_vitality_decay.md`](./03_ultrasonic_tdoa_3d_depth_and_vitality_decay.md) |
| **Part 4** | **Breaking the Pre-Installation Paradox: Native Android & Zero-Install Captive Gateway** | Modern Jetpack Compose Android app, on-device Indic speech triage (Hindi/Telugu/Tamil/etc.), and the 40 KB Zero-Install Captive Portal Micro-PWA with DNS hijacking. | [`04_android_offline_engine_and_zero_install_pwa.md`](./04_android_offline_engine_and_zero_install_pwa.md) |

---

## 🚀 Publishing to Hashnode

You can publish these articles to your Hashnode blog using any of the following methods:

### Method 1: Direct Copy-Paste into Hashnode Editor (Fastest)
1. Open [Hashnode.com](https://hashnode.com) and click **"Write"**.
2. Copy the contents of each markdown file (`01_...`, `02_...`, etc.).
3. The title, subtitle, tags, and cover image are pre-formatted in the markdown frontmatter at the top of each file.
4. Mermaid diagrams and KaTeX math formulas are natively supported by Hashnode!

### Method 2: Hashnode Automatic GitHub Integration (Recommended)
1. Go to your **Hashnode Blog Dashboard** $\to$ **Settings** $\to$ **GitHub**.
2. Connect your GitHub repository: `https://github.com/charan-143/setu-zero-grid-disaster-mesh`.
3. Set the directory path to `blogs`.
4. Any commit pushed to the repo will automatically create or update the posts on Hashnode!

### Method 3: Hashnode MCP Server
If you'd like to publish programmatically via the Hashnode MCP server:
1. Generate a **Personal Access Token** on Hashnode:
   * Go to **Hashnode Profile Settings** $\to$ **Developer** $\to$ **Personal Access Token**.
2. Add your token to `C:\Users\Admin\.gemini\config\mcp_config.json`:
   ```json
   "hashnode": {
     "url": "https://mcp.hashnode.com/mcp",
     "headers": {
       "Authorization": "<YOUR_HASHNODE_PERSONAL_ACCESS_TOKEN>"
     }
   }
   ```
3. Once added, you can instruct the assistant to publish the articles directly to your Hashnode publication!
