# プログラミング学習支援システム MVP

「コンビニ入り口の制御プログラム」課題を通して、学習者の省察的思考を育成する Web アプリケーション。

## 機能

| エリア | 概要 |
|---|---|
| 🧩 プログラム構築 | センサー（条件）とアクションを組み合わせてルールを追加・削除 |
| ▶️ シミュレーション | 昼/夜・人あり/なしを切り替え、ドアとベルの動作をリアルタイム表示 |
| 🤖 AI アドバイス | 現在のプログラムとシミュレーション結果を送信し、ソクラテス式の問いかけを受け取る |

## 技術スタック

- **フロントエンド**: Vue 3 (Composition API) + Vite
- **バックエンド**: Python / FastAPI
- **LLM**: OpenAI API (`gpt-4o-mini`) ／ 未設定時はルールベースのフォールバック応答

---

## セットアップ & 起動方法

### 1. バックエンド

```bash
cd backend

# 仮想環境を作成・有効化
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 依存関係インストール
pip install -r requirements.txt

# (任意) OpenAI API キーを設定
cp .env.example .env
# .env を編集して OPENAI_API_KEY を設定

# サーバー起動
uvicorn main:app --reload
```

バックエンドは http://localhost:8000 で起動します。

### 2. フロントエンド

```bash
cd frontend

npm install
npm run dev
```

フロントエンドは http://localhost:5173 で起動します。

---

## ディレクトリ構成

```
graduation-research/
├── design.md                 # 要件定義
├── README.md
├── backend/
│   ├── main.py               # FastAPI アプリ (エンドポイント・プロンプト生成)
│   ├── requirements.txt
│   ├── .env.example          # 環境変数のテンプレート
│   └── .env                  # (gitignore 推奨) 実際の API キー
└── frontend/
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.js
        └── App.vue           # メイン UI (3 エリアを 1 ファイルに集約)
```

---

## API 仕様

### `POST /api/advice`

**リクエスト**

```json
{
  "rules": [
    {
      "id": "1",
      "conditions": [
        { "type": "person_sensor" },
        { "type": "dark_sensor" }
      ],
      "action": "bell"
    }
  ],
  "environment": {
    "personPresent": true,
    "isDark": true
  },
  "result": {
    "doorOpen": false,
    "bellRinging": true
  }
}
```

**レスポンス**

```json
{
  "message": "夜にお客さんが来ていないとき、ベルはどうなりますか？..."
}
```

---

## 課題の正解プログラム（参考）

| ルール | 条件 | アクション |
|---|---|---|
| 1 | 人感センサーON | ドアを開ける |
| 2 | 人感センサーON **AND** 明るさセンサーON | ベルを鳴らす |

典型的な間違いパターン:
- **パターン A**: 暗いだけでベルが鳴る（人感センサーなし）
- **パターン B**: 夜でないとドアが開かない（ドアルールに明るさセンサーが入っている）
- **パターン D**: ドアのルールとベルのルールを直列につなぐ
