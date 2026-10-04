# 実サービスでの手動確認手順

企画書 §11「実サービスへの結合確認は手動の確認手順として文書化する」に対応する。自動テストは模擬応答(`osm_diff_reviewer/tests/fakes.py`)で行っているので、リリース前と外部仕様の変更が疑われるときにこの手順で確かめる。

## 準備

1. QGIS にプラグインを入れる(リポジトリの `osm_diff_reviewer` フォルダをプロファイルの `python/plugins` に置く)。
2. 照合を1回実行しておく:プロセッシングツールボックスの「OSM Diff Reviewer > Match reference data with OSM」で、`WORKSPACE` に作業用 GeoPackage を指定する。OSM レイヤは version 付きのもの(Overpass の `out meta` や JOSM で保存した .osm など)を使う。
3. プラグインメニューの「Review panel」でドックを開き、作業ファイルを選ぶ。

## JOSM(M3)

前提:JOSM を起動し、設定 > リモート制御 で「リモート制御を有効にする」をオンにする。参照レイヤを送る確認では「データの読み込み」の許可も要る。

| # | 操作 | 期待する結果 |
|---|---|---|
| J1 | JOSM を起動しない状態で、属性差の候補を選び「Open in JOSM」 | ドック下部に「JOSM is not reachable … enable Remote Control」と出る。QGIS は固まらない |
| J2 | JOSM を起動し、属性差または形状差の候補で「Open in JOSM」 | JOSM が候補の周辺(約 50 m の余白)を読み込み、該当する OSM オブジェクトが選択されている |
| J3 | 曖昧の候補で「Open in JOSM」 | 候補の OSM オブジェクトがすべて選択されている |
| J4 | 「Next & open」を数回押す | 一覧の次の候補へ移り、そのつど JOSM が該当箇所を開く |
| J5 | ライセンスが未確認のまま、未登録の候補で「Send reference as a JOSM layer」をオンにして開く | 周辺は開くが参照レイヤは送られず、ライセンスを記録するよう案内が出る |
| J6 | 「Licence…」で確認済みにしてから J5 を繰り返す | JOSM に「Reference: <キー>」レイヤが追加され、属性対応表に基づくタグが付いている。そのレイヤはロックされ、アップロード不可になっている |
| J7 | J2 の後、JOSM の変更セットのタグを見る | ライセンスが確認済みで出典表記があれば `source` に出典が入っている |
| J8 | J6 の直後(参照レイヤが JOSM のアクティブレイヤ)に、別の候補で「Open in JOSM」 | OSM データが参照レイヤではなく通常のデータレイヤに読み込まれる。**未確認事項**:参照レイヤに混ざる、または別レイヤが増える場合は不具合として記録し、`load_and_zoom` の引数を見直す |
| J9 | QGIS の設定でプロキシを有効にした状態で J2 | プロキシを通さずに JOSM が開く |

## Overpass(反映確認)

| # | 操作 | 期待する結果 |
|---|---|---|
| O1 | JOSM で編集・アップロードした候補を選び「Check in OSM」 | 「changed: vN → vM」と出る(Overpass への反映には数分かかることがある) |
| O2 | 編集していない候補で「Check in OSM」 | 「unchanged (vN)」と出る |
| O3 | Settings… で Overpass の URL を存在しないホストにして O2 | 「Overpass API unreachable」と出る |
| O4 | 「Check in OSM」の実行中に QGIS の地図を動かす | 画面が固まらず、終わるとメッセージが出る |

注:Overpass のエンドポイントが相対パスでリダイレクトする場合(`Location: /…`)は失敗する。リダイレクト先の URL を直接設定する。

## MapRoulette(M4)

前提:MapRoulette にログインし、ユーザー設定で API キーを発行する。QGIS の認証設定に「API Header」(ヘッダ名 `apiKey`)か「Basic」(パスワード欄にキー)で保存する。試すときは自分が管理する試験用プロジェクトを使い、作ったチャレンジは確認後に削除する。

| # | 操作 | 期待する結果 |
|---|---|---|
| M1 | ライセンス未確認の参照データでドックの「MapRoulette…」を開く | 書き出しと作成のボタンが押せず、理由が表示される |
| M2 | 確認済みにして「Export GeoJSON…」 | 表示中の候補数のフィーチャを持つ GeoJSON ができる。MapRoulette の Web 画面でこのファイルからチャレンジを作れる |
| M3 | 「Load my projects」 | 管理しているプロジェクトが一覧に出る |
| M4 | 名前と手順を入れて「Create challenge」 | 非公開のチャレンジができ、数分後にタスクが候補数だけ並ぶ。タスク名が `R1\|node/1` の形になっている |
| M5 | MapRoulette でタスクをいくつか「修正済み」「問題なし」「スキップ」にしてから「Sync task states」 | 対応する候補の状態が 反映済み / 対応不要 / 保留 に変わり、メモに MapRoulette のタスク番号が入る |
| M6 | QGIS 側で状態を変えてから、MapRoulette 側は変えずにもう一度同期 | QGIS 側の判定が上書きされない |
| M7 | 認証設定のキーを誤った値にして M3 | 「MapRoulette answered 401」と出る。キーの値は画面にもログにも出ない |

## 記録

確認した日付、QGIS・JOSM のバージョン、結果をこの表の下に追記する。

| 日付 | QGIS | JOSM | 結果 |
|---|---|---|---|
| | | | |
