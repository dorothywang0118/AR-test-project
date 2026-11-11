# Store AR Experience Platform（門市 WebAR 互動平台）

目前進度：**Task 01 — WebAR 技術可行性驗證（POC）**。
目標：手機掃描一張原創圖案 → 畫面中出現 3D 小人偶，點一下會揮手或跳躍。

> 後台、資料庫、發布流程尚未開發（依規格書，POC 通過實機測試後才進入）。

## 全部使用免費技術

| 用途 | 技術 | 費用 |
|---|---|---|
| AR 圖像辨識 | MindAR（MIT 授權，**候選**，尚未鎖定） | 免費 |
| 3D 顯示 | three.js（MIT） | 免費 |
| 網頁建置 | Vite + TypeScript | 免費 |
| 手機測試用主機（HTTPS） | GitHub Pages（公開專案）或 Cloudflare Pages | 免費 |
| 後端 / 資料庫（之後才用） | Supabase 免費方案 | 免費，有額度與閒置暫停限制，屆時再確認 |
| 3D 模型 | 自製原創測試角色（`tools/make_character.py`），之後可用 Blender（免費） | 免費 |

## 在你的電腦上執行（VS Code）

1. 安裝 **Node.js 22 LTS**（https://nodejs.org ，下載 LTS 版一路下一步）。
2. 用 VS Code 開啟 `store-ar-platform` 資料夾，選單 **Terminal → New Terminal**。
3. 依序貼上（每行按 Enter）：
   ```
   cd frontend/customer
   npm install
   npm run dev
   ```
4. 終端機會顯示網址。電腦瀏覽器開啟 `https://localhost:5173` 可看到畫面（電腦沒有圖案可掃，只能看流程）。
   第一次會出現「不安全」警告，這是開發用憑證，選「繼續前往」即可。

## 用手機測試（必須 HTTPS，且一定要實機）

**建議方式：GitHub Pages**（免費、自動 HTTPS、手機直接開）
1. 在 GitHub 建立一個**公開（Public）**專案，並把本資料夾推上去（POC 內只有原創素材，沒有金鑰）。
2. GitHub 專案頁 → **Settings → Pages → Source 選「GitHub Actions」**。
3. 每次推送到 `main`，約 1～2 分鐘後網址就會更新：`https://<你的帳號>.github.io/<專案名>/`。
4. 手機開這個網址，把相機對準 `assets/targets/test-target-001.png`（可在電腦螢幕上全螢幕顯示，或列印出來）。
5. 在網址後面加上 `?debug=1` 可顯示偵測紀錄（FPS、第一次辨識所花時間），方便填測試表。

詳細步驟與記錄表：`docs/testing.md`。

## 資料夾說明

| 資料夾 | 內容 |
|---|---|
| `frontend/customer/` | 顧客端網頁（目前唯一可執行的部分） |
| `frontend/admin/`、`backend/` | 預留給後台與後端，目前是空的 |
| `shared/types/` | 前後台共用的資料格式（活動設定檔 manifest） |
| `assets/` | 原創測試圖案、小人偶 GLB、編譯好的辨識資料 |
| `tools/` | 產生素材、編譯辨識資料、模擬相機測試的小工具（Python） |
| `docs/` | 技術評估、架構、測試、工作清單 |

## 更換圖案或角色（目前仍需用工具，後台完成後就不需要）

```
python3 tools/make_target.py assets/targets/新圖案.png        # 或放你自己的圖
python3 tools/compile_target.py assets/targets/新圖案.mind assets/targets/新圖案.png
```
再把 `.mind`、`.glb` 放進 `frontend/customer/public/campaign/`，並修改同資料夾的 `campaign.json`。
（`tools/` 需要 Python 3、`pip install playwright pillow numpy` 與 Chrome。）

## 素材與 IP

測試用的圖案與角色皆為**原創**。未取得授權前，不得放入任何 Nintendo 角色、圖片、模型或商標（規格書第 14 節）。
