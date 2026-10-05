<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="ja">
  <context>
    <name>OsmDiffReviewer</name>
    <message>
      <source>Unreviewed</source>
      <translation>未確認</translation>
    </message>
    <message>
      <source>Needs edit</source>
      <translation>要編集</translation>
    </message>
    <message>
      <source>Done</source>
      <translation>反映済み</translation>
    </message>
    <message>
      <source>Not needed (reference is wrong)</source>
      <translation>対応不要(参照側の誤り)</translation>
    </message>
    <message>
      <source>Not needed (OSM is right)</source>
      <translation>対応不要(OSM が正しい)</translation>
    </message>
    <message>
      <source>On hold</source>
      <translation>保留</translation>
    </message>
    <message>
      <source>No MapRoulette API key is configured. Choose or create an authentication configuration.</source>
      <translation>MapRoulette の API キーが設定されていません。認証設定を選ぶか作成してください。</translation>
    </message>
    <message>
      <source>Authentication configuration {!r} has no API key (use API Header with 'apiKey', or Basic with the key as password).</source>
      <translation>認証設定 {!r} に API キーがありません(「API Header」でヘッダ名 apiKey、または「Basic」のパスワード欄にキーを入れてください)。</translation>
    </message>
    <message>
      <source>Authentication configuration {!r} could not be read.</source>
      <translation>認証設定 {!r} を読み込めませんでした。</translation>
    </message>
    <message>
      <source>No licence record for this reference source; record and confirm it first.</source>
      <translation>この参照データのライセンスが記録されていません。先に記録して確認してください。</translation>
    </message>
    <message>
      <source>The licence of reference source '{}' is not confirmed; confirm that it may be used in OSM before exporting reference data.</source>
      <translation>参照データ「{}」のライセンスが確認されていません。参照データを外部に出す前に、OSM で利用できることを確認してください。</translation>
    </message>
    <message>
      <source>Not an Overpass API URL: {!r}</source>
      <translation>Overpass API の URL ではありません:{!r}</translation>
    </message>
    <message>
      <source>Overpass API answered {}: {}</source>
      <translation>Overpass API がエラーを返しました({}):{}</translation>
    </message>
    <message>
      <source>Overpass API could not complete the query: {}</source>
      <translation>Overpass API が問い合わせを完了できませんでした:{}</translation>
    </message>
    <message>
      <source>Overpass API unreachable: {}</source>
      <translation>Overpass API に接続できません:{}</translation>
    </message>
    <message>
      <source>Unexpected Overpass response: {}</source>
      <translation>Overpass API の応答を解釈できません:{}</translation>
    </message>
    <message>
      <source>Workspace not found: {}</source>
      <translation>作業ファイルが見つかりません:{}</translation>
    </message>
    <message>
      <source>{} is not a workspace (missing tables: {})</source>
      <translation>{} は作業ファイルではありません(足りないテーブル:{})</translation>
    </message>
    <message>
      <source>Unknown review status: {!r}</source>
      <translation>不明なレビュー状態です:{!r}</translation>
    </message>
    <message>
      <source>Run {} not found</source>
      <translation>実行 {} が見つかりません</translation>
    </message>
    <message>
      <source>Cannot create workspace {}: {}</source>
      <translation>作業ファイル {} を作成できません:{}</translation>
    </message>
    <message>
      <source>Cannot open workspace {}: {}</source>
      <translation>作業ファイル {} を開けません:{}</translation>
    </message>
    <message>
      <source>Workspace {}: {}</source>
      <translation>作業ファイル {}:{}</translation>
    </message>
    <message>
      <source>The candidate has no geometry to open.</source>
      <translation>この候補には開くための形状がありません。</translation>
    </message>
    <message>
      <source>The candidate covers too large an area to download in JOSM.</source>
      <translation>この候補は範囲が広すぎて JOSM で読み込めません。</translation>
    </message>
    <message>
      <source>The reference feature has no geometry.</source>
      <translation>参照地物に形状がありません。</translation>
    </message>
    <message>
      <source>JOSM Remote Control must be on this computer (127.0.0.1 or localhost), not {!r}</source>
      <translation>JOSM リモート制御はこのコンピュータ上のアドレス(127.0.0.1 または localhost)にしてください:{!r}</translation>
    </message>
    <message>
      <source>Give only the address and port of JOSM Remote Control, e.g. http://127.0.0.1:8111 (not {!r})</source>
      <translation>JOSM リモート制御はアドレスとポートだけを指定してください(例:http://127.0.0.1:8111)。指定値:{!r}</translation>
    </message>
    <message>
      <source>This kind of reference geometry cannot be sent to JOSM.</source>
      <translation>この種類の形状の参照地物は JOSM に送れません。</translation>
    </message>
    <message>
      <source>JOSM refused the request ({}): {}</source>
      <translation>JOSM が要求を拒否しました({}):{}</translation>
    </message>
    <message>
      <source>The reference feature is too large to send through Remote Control.</source>
      <translation>参照地物が大きすぎて、リモート制御では送れません。</translation>
    </message>
    <message>
      <source>JOSM is not reachable at {}. Start JOSM and enable Remote Control (Preferences &gt; Remote Control).</source>
      <translation>{} の JOSM に接続できません。JOSM を起動し、リモート制御を有効にしてください(設定 &gt; リモート制御)。</translation>
    </message>
    <message>
      <source>Unexpected answer from {}; is this JOSM?</source>
      <translation>{} から想定外の応答がありました。JOSM ですか?</translation>
    </message>
    <message>
      <source>Reference: {}</source>
      <translation>参照: {}</translation>
    </message>
    <message>
      <source>There are no candidates to export.</source>
      <translation>書き出す候補がありません。</translation>
    </message>
    <message>
      <source>Use https for MapRoulette; the API key must not be sent unencrypted.</source>
      <translation>MapRoulette には https を使ってください。API キーを暗号化せずに送ることはできません。</translation>
    </message>
    <message>
      <source>A MapRoulette API key is required.</source>
      <translation>MapRoulette の API キーが必要です。</translation>
    </message>
    <message>
      <source>Choose a MapRoulette project.</source>
      <translation>MapRoulette のプロジェクトを選んでください。</translation>
    </message>
    <message>
      <source>A challenge needs a name and instructions.</source>
      <translation>チャレンジには名称と手順が必要です。</translation>
    </message>
    <message>
      <source>There are no candidates to send.</source>
      <translation>送る候補がありません。</translation>
    </message>
    <message>
      <source>MapRoulette did not return the new challenge id.</source>
      <translation>MapRoulette から新しいチャレンジの ID が返ってきませんでした。</translation>
    </message>
    <message>
      <source>Candidate {} has no geometry.</source>
      <translation>候補 {} に形状がありません。</translation>
    </message>
    <message>
      <source>Not a MapRoulette API URL: {!r}</source>
      <translation>MapRoulette API の URL ではありません:{!r}</translation>
    </message>
    <message>
      <source>MapRoulette answered {}: {}</source>
      <translation>MapRoulette がエラーを返しました({}):{}</translation>
    </message>
    <message>
      <source>Unexpected MapRoulette response: {}</source>
      <translation>MapRoulette の応答を解釈できません:{}</translation>
    </message>
    <message>
      <source>MapRoulette unreachable: {}</source>
      <translation>MapRoulette に接続できません:{}</translation>
    </message>
    <message>
      <source>Working…</source>
      <translation>処理中…</translation>
    </message>
    <message>
      <source>This candidate has no OSM object yet; re-run matching after editing to see it in OSM.</source>
      <translation>この候補にはまだ OSM 地物がありません。編集後に照合を再実行すると OSM での状態がわかります。</translation>
    </message>
    <message>
      <source>Opened {} in JOSM. Update the status here when done.</source>
      <translation>{} を JOSM で開きました。編集が終わったらここで状態を更新してください。</translation>
    </message>
    <message>
      <source>{} changed: v{} → v{}. If this was your edit, set the status to Done.</source>
      <translation>{} は変更されています:v{} → v{}。ご自身の編集であれば状態を「反映済み」にしてください。</translation>
    </message>
    <message>
      <source>the area of {}</source>
      <translation>{} の周辺</translation>
    </message>
    <message>
      <source>{} is no longer in OSM (deleted, or not yet in Overpass).</source>
      <translation>{} は OSM にありません(削除済み、または Overpass に未反映)。</translation>
    </message>
    <message>
      <source>{} is unchanged (v{}).</source>
      <translation>{} は変更されていません(v{})。</translation>
    </message>
    <message>
      <source>Reference layer not sent: {} Use the Licence… button to record it.</source>
      <translation>参照レイヤは送りませんでした:{}「ライセンス…」ボタンで記録してください。</translation>
    </message>
    <message>
      <source>Not checked</source>
      <translation>未確認</translation>
    </message>
    <message>
      <source>Confirmed: may be used in OSM</source>
      <translation>確認済み:OSM で利用できる</translation>
    </message>
    <message>
      <source>Not compatible with OSM</source>
      <translation>不可:OSM で利用できない</translation>
    </message>
    <message>
      <source>Reference data licence</source>
      <translation>参照データのライセンス</translation>
    </message>
    <message>
      <source>Reference source</source>
      <translation>参照データ</translation>
    </message>
    <message>
      <source>Licence</source>
      <translation>ライセンス</translation>
    </message>
    <message>
      <source>Attribution</source>
      <translation>出典表記</translation>
    </message>
    <message>
      <source>Use in OSM</source>
      <translation>OSM での利用</translation>
    </message>
    <message>
      <source>Evidence URL</source>
      <translation>根拠 URL</translation>
    </message>
    <message>
      <source>Reference data can only be exported (JOSM reference layer, GeoJSON, MapRoulette) when its use in OSM is confirmed. Matching and reviewing work regardless. Adding external data to OSM may fall under the &lt;a href="{}"&gt;Import Guidelines&lt;/a&gt;; consult your local community before large changes.</source>
      <translation>参照データを外部に出す操作(JOSM への参照レイヤ送信、GeoJSON 書き出し、MapRoulette)は、OSM での利用が確認済みの場合だけ行えます。照合とレビューはいつでも行えます。外部データを OSM に取り込む作業は&lt;a href="{}"&gt;インポートガイドライン&lt;/a&gt;の対象になることがあります。大きな変更の前には地域コミュニティに相談してください。</translation>
    </message>
    <message>
      <source>MapRoulette</source>
      <translation>MapRoulette</translation>
    </message>
    <message>
      <source>Task description; {name} is replaced by a task property, e.g. {ref_key}, {@id}, {ref:FIELD}</source>
      <translation>タスクの説明文。{name} はタスクのプロパティに置き換わります(例:{ref_key}、{@id}、{ref:FIELD}。FIELD は参照側のフィールド名)</translation>
    </message>
    <message>
      <source>Line-by-line GeoJSON (one task per line)</source>
      <translation>行区切り GeoJSON(1行1タスク)</translation>
    </message>
    <message>
      <source>Export GeoJSON…</source>
      <translation>GeoJSON に書き出す…</translation>
    </message>
    <message>
      <source>1. Tasks as GeoJSON</source>
      <translation>1. タスクを GeoJSON に書き出す</translation>
    </message>
    <message>
      <source>Task description</source>
      <translation>タスクの説明文</translation>
    </message>
    <message>
      <source>Store the MapRoulette API key as 'API Header' (header apiKey) or as the password of a 'Basic' config</source>
      <translation>MapRoulette の API キーは「API Header」(ヘッダ名 apiKey)、または「Basic」のパスワード欄に保存してください</translation>
    </message>
    <message>
      <source>MapRoulette server</source>
      <translation>MapRoulette サーバー</translation>
    </message>
    <message>
      <source>API URL</source>
      <translation>API の URL</translation>
    </message>
    <message>
      <source>API key</source>
      <translation>API キー</translation>
    </message>
    <message>
      <source>Load my projects</source>
      <translation>管理中のプロジェクトを読み込む</translation>
    </message>
    <message>
      <source>Changeset comment, e.g. #hashtag</source>
      <translation>変更セットのコメント(例:#ハッシュタグ)</translation>
    </message>
    <message>
      <source>Publish immediately</source>
      <translation>すぐに公開する</translation>
    </message>
    <message>
      <source>Leave off and publish on MapRoulette after consulting the local community</source>
      <translation>オフのまま作成し、地域コミュニティに相談してから MapRoulette で公開してください</translation>
    </message>
    <message>
      <source>Create challenge</source>
      <translation>チャレンジを作成</translation>
    </message>
    <message>
      <source>2. Create a challenge</source>
      <translation>2. チャレンジを作成する</translation>
    </message>
    <message>
      <source>Project</source>
      <translation>プロジェクト</translation>
    </message>
    <message>
      <source>Name</source>
      <translation>名称</translation>
    </message>
    <message>
      <source>Description</source>
      <translation>説明</translation>
    </message>
    <message>
      <source>Instructions</source>
      <translation>手順</translation>
    </message>
    <message>
      <source>Changeset comment</source>
      <translation>変更セットのコメント</translation>
    </message>
    <message>
      <source>Sync task states</source>
      <translation>タスクの状態を同期</translation>
    </message>
    <message>
      <source>3. Progress</source>
      <translation>3. 進捗</translation>
    </message>
    <message>
      <source>Load MapRoulette projects</source>
      <translation>MapRoulette のプロジェクトを読み込み中</translation>
    </message>
    <message>
      <source>Create MapRoulette challenge</source>
      <translation>MapRoulette のチャレンジを作成中</translation>
    </message>
    <message>
      <source>Sync MapRoulette tasks</source>
      <translation>MapRoulette のタスクを同期中</translation>
    </message>
    <message>
      <source>Challenge</source>
      <translation>チャレンジ</translation>
    </message>
    <message>
      <source>Export is blocked: the licence of this reference data is not confirmed (use Licence… in the review panel). Progress sync of existing challenges still works.</source>
      <translation>書き出しは止めています:この参照データのライセンスが確認されていません(レビューパネルの「ライセンス…」で記録してください)。作成済みチャレンジの進捗同期は行えます。</translation>
    </message>
    <message>
      <source>Export tasks</source>
      <translation>タスクの書き出し</translation>
    </message>
    <message>
      <source>GeoJSON (*.geojson *.json)</source>
      <translation>GeoJSON (*.geojson *.json)</translation>
    </message>
    <message>
      <source>No challenge has been created for this reference source yet.</source>
      <translation>この参照データのチャレンジはまだ作成されていません。</translation>
    </message>
    <message>
      <source>Please wait until the current request has finished.</source>
      <translation>実行中の処理が終わるまでお待ちください。</translation>
    </message>
    <message>
      <source>{} candidate(s) of '{}' — those currently shown in the review panel.</source>
      <translation>「{1}」の候補 {0} 件(レビューパネルに表示中のもの)</translation>
    </message>
    <message>
      <source>Wrote {} task(s) to {}</source>
      <translation>{} 件のタスクを {} に書き出しました</translation>
    </message>
    <message>
      <source>{} project(s) loaded.</source>
      <translation>{} 件のプロジェクトを読み込みました。</translation>
    </message>
    <message>
      <source>Created challenge {} with {} task(s). MapRoulette builds the tasks in the background.</source>
      <translation>チャレンジ {} を {} 件のタスクで作成しました。タスクは MapRoulette 側で順次作られます。</translation>
    </message>
    <message>
      <source>Updated {} review(s); {} unchanged; {} not in the latest run; {} unknown task(s).</source>
      <translation>{} 件の判定を更新しました。変化なし {} 件、最新の照合結果にない候補 {} 件、不明なタスク {} 件。</translation>
    </message>
    <message>
      <source>Licence confirmed. Before publishing a large challenge, consult your local community (&lt;a href="{}"&gt;Import Guidelines&lt;/a&gt;).</source>
      <translation>ライセンスは確認済みです。大きなチャレンジを公開する前に地域コミュニティに相談してください(&lt;a href="{}"&gt;インポートガイドライン&lt;/a&gt;)。</translation>
    </message>
    <message>
      <source>OSM Diff Reviewer</source>
      <translation>OSM Diff Reviewer</translation>
    </message>
    <message>
      <source>GeoPackage (*.gpkg)</source>
      <translation>GeoPackage (*.gpkg)</translation>
    </message>
    <message>
      <source>Workspace GeoPackage</source>
      <translation>作業用 GeoPackage</translation>
    </message>
    <message>
      <source>Run matching…</source>
      <translation>照合を実行…</translation>
    </message>
    <message>
      <source>Reload</source>
      <translation>再読み込み</translation>
    </message>
    <message>
      <source>Show the latest run, e.g. after running matching from the Processing toolbox</source>
      <translation>最新の照合結果を表示します(プロセッシングツールボックスから実行した後など)</translation>
    </message>
    <message>
      <source>Licence…</source>
      <translation>ライセンス…</translation>
    </message>
    <message>
      <source>All classifications</source>
      <translation>すべての分類</translation>
    </message>
    <message>
      <source>All statuses</source>
      <translation>すべての状態</translation>
    </message>
    <message>
      <source>Show matches</source>
      <translation>一致も表示</translation>
    </message>
    <message>
      <source>Show 'not needed'</source>
      <translation>「対応不要」も表示</translation>
    </message>
    <message>
      <source>Recheck only</source>
      <translation>要再確認のみ</translation>
    </message>
    <message>
      <source>Note</source>
      <translation>メモ</translation>
    </message>
    <message>
      <source>Save</source>
      <translation>保存</translation>
    </message>
    <message>
      <source>Next candidate</source>
      <translation>次の候補</translation>
    </message>
    <message>
      <source>Open in JOSM</source>
      <translation>JOSM で開く</translation>
    </message>
    <message>
      <source>Next &amp;&amp; open</source>
      <translation>次を開く</translation>
    </message>
    <message>
      <source>Check in OSM</source>
      <translation>OSM で反映確認</translation>
    </message>
    <message>
      <source>Re-read the OSM version via Overpass to see whether the object changed</source>
      <translation>Overpass で OSM 地物の version を読み直し、変化があったか確かめます</translation>
    </message>
    <message>
      <source>Send reference as a JOSM layer (missing only)</source>
      <translation>参照地物を JOSM の別レイヤとして送る(未登録の候補のみ)</translation>
    </message>
    <message>
      <source>Never uploaded; needs a confirmed licence of the reference data</source>
      <translation>アップロードはされません。参照データのライセンスが確認済みであることが必要です</translation>
    </message>
    <message>
      <source>MapRoulette…</source>
      <translation>MapRoulette…</translation>
    </message>
    <message>
      <source>Export or send the candidates shown in the list as MapRoulette tasks</source>
      <translation>一覧に表示中の候補を MapRoulette のタスクとして書き出す・送る</translation>
    </message>
    <message>
      <source>Settings…</source>
      <translation>設定…</translation>
    </message>
    <message>
      <source>Saved.</source>
      <translation>保存しました。</translation>
    </message>
    <message>
      <source>Item</source>
      <translation>項目</translation>
    </message>
    <message>
      <source>Reference</source>
      <translation>参照</translation>
    </message>
    <message>
      <source>OSM</source>
      <translation>OSM</translation>
    </message>
    <message>
      <source>Choose or create a workspace GeoPackage first.</source>
      <translation>先に作業用 GeoPackage を選ぶか作成してください。</translation>
    </message>
    <message>
      <source>Run matching first.</source>
      <translation>先に照合を実行してください。</translation>
    </message>
    <message>
      <source>score</source>
      <translation>スコア</translation>
    </message>
    <message>
      <source>alternatives</source>
      <translation>他の候補</translation>
    </message>
    <message>
      <source>Changed since the decision: recheck</source>
      <translation>判定後に変化あり:要再確認</translation>
    </message>
    <message>
      <source>Reference key</source>
      <translation>参照キー</translation>
    </message>
    <message>
      <source>Classification</source>
      <translation>分類</translation>
    </message>
    <message>
      <source>Version change</source>
      <translation>版間の変化</translation>
    </message>
    <message>
      <source>Score</source>
      <translation>スコア</translation>
    </message>
    <message>
      <source>Status</source>
      <translation>状態</translation>
    </message>
    <message>
      <source>Recheck</source>
      <translation>要再確認</translation>
    </message>
    <message>
      <source>Match</source>
      <translation>一致</translation>
    </message>
    <message>
      <source>Missing in OSM</source>
      <translation>未登録</translation>
    </message>
    <message>
      <source>Geometry differs</source>
      <translation>形状差</translation>
    </message>
    <message>
      <source>Attributes differ</source>
      <translation>属性差</translation>
    </message>
    <message>
      <source>Ambiguous</source>
      <translation>曖昧</translation>
    </message>
    <message>
      <source>OSM only</source>
      <translation>OSM のみ</translation>
    </message>
    <message>
      <source>Added</source>
      <translation>追加</translation>
    </message>
    <message>
      <source>Removed</source>
      <translation>削除</translation>
    </message>
    <message>
      <source>Changed</source>
      <translation>変更</translation>
    </message>
    <message>
      <source>already in OSM</source>
      <translation>OSM に既にある</translation>
    </message>
    <message>
      <source>not in OSM</source>
      <translation>OSM にない</translation>
    </message>
    <message>
      <source>still in OSM</source>
      <translation>OSM にまだある</translation>
    </message>
    <message>
      <source>gone from OSM</source>
      <translation>OSM から消えている</translation>
    </message>
    <message>
      <source>OSM has the old state</source>
      <translation>OSM は旧状態のまま</translation>
    </message>
    <message>
      <source>OSM already updated</source>
      <translation>OSM は更新済み</translation>
    </message>
    <message>
      <source>undecided</source>
      <translation>判定不能</translation>
    </message>
    <message>
      <source>ambiguous</source>
      <translation>曖昧</translation>
    </message>
    <message>
      <source>OSM Diff Reviewer settings</source>
      <translation>OSM Diff Reviewer の設定</translation>
    </message>
    <message>
      <source>JOSM Remote Control</source>
      <translation>JOSM リモート制御</translation>
    </message>
    <message>
      <source>Overpass API</source>
      <translation>Overpass API</translation>
    </message>
    <message>
      <source>Review panel</source>
      <translation>レビューパネル</translation>
    </message>
    <message>
      <source>Match reference data with OSM</source>
      <translation>参照データと OSM を照合</translation>
    </message>
    <message>
      <source>Matches reference features (points, lines and polygons) with OSM features and classifies each pair as match, missing, geometry_diff, attribute_diff, ambiguous or osm_only. Distances are measured in the project CRS when it is projected in metres, otherwise in the UTM zone of the reference data. Without a reference key field, a hash of geometry and attributes is used; the key then changes whenever the reference feature changes. Lines that are segmented differently in OSM are reported as ambiguous. With a workspace GeoPackage, the run is recorded and earlier review decisions are carried over; pairs whose reference or OSM side changed since the decision are flagged for recheck.</source>
      <translation>参照地物(ポイント・ライン・ポリゴン)を OSM 地物と照合し、組ごとに 一致(match)・未登録(missing)・形状差(geometry_diff)・属性差(attribute_diff)・曖昧(ambiguous)・OSM のみ(osm_only)に分類します。距離はプロジェクトの座標系がメートル単位の投影座標系ならその座標系で、そうでなければ参照データの UTM 帯で測ります。参照 ID フィールドを指定しない場合は形状と属性のハッシュをキーにするため、参照地物が変わるとキーも変わります。OSM 側で区切り方の違うラインは「曖昧」になります。作業用 GeoPackage を指定すると実行結果を記録し、前回までの判定を引き継ぎます。判定後に参照側または OSM 側が変わった組には「要再確認」の印が付きます。</translation>
    </message>
    <message>
      <source>Compare reference versions with OSM</source>
      <translation>参照データの版間差分を OSM と照合</translation>
    </message>
    <message>
      <source>Compares an old and a new version of the reference data by their ID field and matches only the changes against OSM: for an added feature, whether it is already in OSM; for a removed one, whether it is still in OSM; for a changed one, whether OSM is closer to the old or the new version. Both versions are matched as a whole, so unchanged features keep their OSM objects. The ID field must exist in both versions and be stable.</source>
      <translation>参照データの旧版と新版を ID フィールドで突き合わせ、変化のあった地物だけを OSM と照合します。追加は OSM に既にあるか、削除は OSM にまだあるか、変更は OSM が旧版と新版のどちらに近いかを判定します。両方の版をそれぞれ全体として照合するため、変化のない地物の OSM 地物は横取りされません。ID フィールドは両方の版にあり、版をまたいで変わらないものが必要です。</translation>
    </message>
    <message>
      <source>Candidates</source>
      <translation>候補</translation>
    </message>
    <message>
      <source>Changes</source>
      <translation>変化</translation>
    </message>
    <message>
      <source>Reference layer</source>
      <translation>参照レイヤ</translation>
    </message>
    <message>
      <source>Reference ID field (stable key)</source>
      <translation>参照 ID フィールド(安定キー)</translation>
    </message>
    <message>
      <source>Report OSM-only features (reference data is exhaustive)</source>
      <translation>OSM のみの地物も出す(参照データが網羅的な場合)</translation>
    </message>
    <message>
      <source>No reference ID field: keys are hashes and change whenever a reference feature changes.</source>
      <translation>参照 ID フィールドの指定がありません。キーはハッシュになり、参照地物が変わるたびに変わります。</translation>
    </message>
    <message>
      <source>Old reference version</source>
      <translation>参照データの旧版</translation>
    </message>
    <message>
      <source>New reference version</source>
      <translation>参照データの新版</translation>
    </message>
    <message>
      <source>Reference ID field (in both versions)</source>
      <translation>参照 ID フィールド(両方の版にあるもの)</translation>
    </message>
    <message>
      <source>{} reference feature(s) with unsupported geometry were skipped.</source>
      <translation>対応していない形状の参照地物 {} 件を飛ばしました。</translation>
    </message>
    <message>
      <source>The ID field {!r} must exist in both versions.</source>
      <translation>ID フィールド {!r} が両方の版にありません。</translation>
    </message>
    <message>
      <source>{} change(s) with unsupported geometry were skipped, e.g. {}</source>
      <translation>対応していない形状の変化 {} 件を飛ばしました(例:{})</translation>
    </message>
    <message>
      <source>OSM layer</source>
      <translation>OSM レイヤ</translation>
    </message>
    <message>
      <source>OSM type field</source>
      <translation>OSM 種別のフィールド</translation>
    </message>
    <message>
      <source>OSM ID field</source>
      <translation>OSM ID のフィールド</translation>
    </message>
    <message>
      <source>OSM version field</source>
      <translation>OSM version のフィールド</translation>
    </message>
    <message>
      <source>Profile (JSON)</source>
      <translation>プロファイル(JSON)</translation>
    </message>
    <message>
      <source>Workspace (GeoPackage)</source>
      <translation>作業用 GeoPackage</translation>
    </message>
    <message>
      <source>Reference source name (defaults to the layer name)</source>
      <translation>参照データ名(省略時はレイヤ名)</translation>
    </message>
    <message>
      <source>Run ID</source>
      <translation>実行 ID</translation>
    </message>
    <message>
      <source>Invalid input layer</source>
      <translation>入力レイヤが正しくありません</translation>
    </message>
    <message>
      <source>The OSM layer has no version information; changes on the OSM side cannot be detected.</source>
      <translation>OSM レイヤに version の情報がないため、OSM 側の変化は検出できません。</translation>
    </message>
    <message>
      <source>Working CRS: {}</source>
      <translation>作業座標系:{}</translation>
    </message>
    <message>
      <source>Recorded run {} in {}</source>
      <translation>実行 {} を {} に記録しました</translation>
    </message>
    <message>
      <source>The layer {} has no features</source>
      <translation>レイヤ {} に地物がありません</translation>
    </message>
    <message>
      <source>Using the recorded reference ID field: {}</source>
      <translation>記録済みの参照 ID フィールドを使います:{}</translation>
    </message>
    <message>
      <source>The reference ID field changed from {} to {}; earlier review decisions will not carry over.</source>
      <translation>参照 ID フィールドが {} から {} に変わりました。これまでの判定は引き継がれません。</translation>
    </message>
    <message>
      <source>{} reference key(s) are not unique, e.g. {}; review decisions cannot tell them apart.</source>
      <translation>参照キー {} 件が重複しています(例:{})。判定を区別できません。</translation>
    </message>
    <message>
      <source>The data or ID field of '{}' changed, so its licence is unconfirmed again.</source>
      <translation>「{}」のデータまたは ID フィールドが変わったため、ライセンスは未確認に戻りました。</translation>
    </message>
  </context>
</TS>
