# プログラミング学習支援システム

「コンビニ入り口の制御プログラム」課題を通して、学習者の省察的思考を育成する Web アプリケーション。

## 実験の目的

中山ら（2019）の研究では、複数の児童が**ペア対話・全体対話**を行うことで省察的思考が育成されることが示された。  
本システムでは、その**対話相手を AI に置き換えた場合**でも同様の省察的思考が促進されるかを検証する。

## 機能

| エリア | 概要 |
|---|---|
| プログラム構築 | センサー（条件）とアクションを組み合わせてルールを追加・削除 |
| シミュレーション | 昼/夜・人あり/なしの4シナリオで動作をリアルタイム確認 |
| AI 対話 | 自由入力でAIに話しかけ、ソクラテス式の問いかけで省察を促す |

## 課題の内容

コンビニの入り口センサーを使って、以下の条件を満たすプログラムを作る。

- 人が来たら → **自動ドアを開ける**（昼夜問わず）
- 夜に人が来たら → **チャイムを鳴らす**（昼は鳴らさない）

**正解プログラム（参考）**

| ルール | 条件 | アクション |
|---|---|---|
| 1 | 人感センサーON | ドアを開ける |
| 2 | 人感センサーON **AND** 明るさセンサーON（夜） | チャイムを鳴らす |

## 技術スタック

- **フロントエンド**: Vue 3 (Composition API) + Vite
- **バックエンド**: Python / FastAPI（ポート 8001）
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

# サーバー起動（ポート 8001）
uvicorn main:app --reload --port 8001
```

バックエンドは http://localhost:8001 で起動します。

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
├── README.md
├── backend/
│   ├── main.py               # FastAPI アプリ（エンドポイント・プロンプト生成）
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.js
        └── App.vue           # メイン UI（3 エリアを 1 ファイルに集約）
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
    "bellRinging": true,
    "doorCorrect": false,
    "bellCorrect": true,
    "allCorrect": false
  },
  "history": [
    { "role": "ai", "text": "こんにちは！..." },
    { "role": "user", "text": "夜だけベルが鳴るようにしたい" }
  ]
}
```

**レスポンス**

```json
{
  "message": "夜にお客さんが来ていないとき、ベルはどうなりますか？..."
}
```

---

## 参考論文

中山 貴司, 川崎 弘作, 木下 博義（2019）「プログラミング学習を通した批判的思考の育成に関する研究：小学6年理科「電気の利用」単元における省察的思考に着目して」日本教科教育学会誌, Vol.21, No.1, pp.53-67
