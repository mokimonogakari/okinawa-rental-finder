# LINE Messaging API セットアップガイド

LINE Notify は 2025年3月31日に廃止されたため、本プロジェクトでは **LINE Messaging API** を使用して通知を送信します。

## 前提条件

- LINEアカウントを持っていること
- 通知を受け取りたい人全員がLINEを利用していること

## 1. LINE Developersコンソールでチャネル作成

### 1-1. ログイン

1. [LINE Developers](https://developers.line.biz/) にアクセス
2. 普段使っているLINEアカウントでログイン

### 1-2. プロバイダー作成

1. コンソール画面で **「プロバイダー作成」** をクリック
2. プロバイダー名を入力（例: `沖縄賃貸ファインダー`）
3. 「作成」をクリック

### 1-3. Messaging APIチャネル作成

1. プロバイダー画面で **「Messaging API」** をクリック
2. 以下を入力:

| 項目 | 入力例 |
|------|--------|
| チャネル名 | `沖縄賃貸通知` |
| チャネル説明 | `新着賃貸物件の通知` |
| 大業種 | `個人` |
| 小業種 | `個人（その他）` |
| メールアドレス | 自分のメールアドレス |

3. 利用規約に同意して「作成」

## 2. チャネルアクセストークンの発行

1. 作成したチャネルの **「Messaging API設定」** タブを開く
2. ページ最下部の **「チャネルアクセストークン（長期）」** セクション
3. **「発行」** をクリック
4. 表示されたトークンをコピーして安全に保管

> このトークンが `LINE_CHANNEL_ACCESS_TOKEN` 環境変数に設定する値です。

## 3. 応答設定の変更

「Messaging API設定」画面の **「LINE公式アカウント機能」** セクション:

1. **応答メッセージ** → 「編集」→ **無効** にする
2. **あいさつメッセージ** → 任意（無効でもOK）

> これを無効にしないと、ユーザーがメッセージを送るたびに自動応答が返ってしまいます。

## 4. 友だち追加

「Messaging API設定」タブに表示されている **QRコード** を使って、通知を受け取りたい全員が友だち追加します。

1. LINEアプリを開く
2. 「友だち追加」→「QRコード」
3. QRコードを読み取って友だち追加

## 5. ユーザーIDの取得

### 自分のユーザーID

「**チャネル基本設定**」タブの最下部に **「あなたのユーザーID」** が表示されています。
`U` で始まる33文字の文字列です（例: `U1234567890abcdef1234567890abcdef`）。

### 他の人のユーザーID

友だち追加済みの他のユーザーのIDは、以下の方法で取得できます:

**方法A: Webhook経由（推奨）**

Webhook URLを設定すると、友だち追加時に `follow` イベントが送信され、そこにユーザーIDが含まれます。本アプリの管理画面（⚙️ 管理 → LINE設定）からWebhook URLを設定できます。

**方法B: LINE Developers コンソール**

友だち一覧APIを使ってユーザーIDを取得:

```bash
curl -s -H "Authorization: Bearer {チャネルアクセストークン}" \
  https://api.line.me/v2/bot/followers/ids
```

## 6. 環境変数の設定

取得した情報を `.env` ファイルに設定します:

```bash
# LINE Messaging API
LINE_CHANNEL_ACCESS_TOKEN=発行したチャネルアクセストークン
LINE_USER_IDS=Uxxxx,Uyyyy
```

- `LINE_CHANNEL_ACCESS_TOKEN`: 手順2で発行したトークン
- `LINE_USER_IDS`: 通知を送りたいユーザーIDをカンマ区切りで指定

### VPSへの設定

```bash
ssh ubuntu@<VPS_IP>
echo 'LINE_CHANNEL_ACCESS_TOKEN=your_token_here' >> /home/ubuntu/okinawa-rental-finder/.env
echo 'LINE_USER_IDS=Uxxxx,Uyyyy' >> /home/ubuntu/okinawa-rental-finder/.env
```

## 7. 動作確認

### Web UIから確認

1. https://test.supportforokinawa.jp/rental/ にアクセス
2. サイドバーの「🔔 通知設定」を開く
3. 「テスト通知を送信」ボタンをクリック

### コマンドラインから確認

```bash
cd /home/ubuntu/okinawa-rental-finder
.venv/bin/python -m src.notification.line_notify --test
```

## 料金について

| プラン | 月額 | 無料メッセージ数 |
|--------|------|-----------------|
| コミュニケーションプラン | 0円 | 200通/月 |
| ライトプラン | 5,000円 | 5,000通/月 |

2人への毎日通知であれば、**コミュニケーションプラン（無料）で十分**です。
（1日1通 × 2人 × 30日 = 60通/月）

## トラブルシューティング

### 通知が届かない

1. 友だち追加済みか確認
2. `LINE_CHANNEL_ACCESS_TOKEN` が正しいか確認
3. `LINE_USER_IDS` のユーザーIDが正しいか確認（`U` で始まる33文字）
4. チャネルのステータスが「利用中」か確認

### 403エラー

- チャネルアクセストークンが無効または期限切れ → 再発行してください

### 429エラー（レート制限）

- 短時間に大量送信した場合に発生
- 通常の利用（日次通知）では発生しません

## 参考リンク

- [LINE Messaging API ドキュメント](https://developers.line.biz/ja/docs/messaging-api/)
- [Push Message API リファレンス](https://developers.line.biz/ja/reference/messaging-api/#send-push-message)
- [料金プラン](https://www.lycbiz.com/jp/service/line-official-account/plan/)
