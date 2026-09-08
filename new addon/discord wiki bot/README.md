python -m app.bot

# Discord Wiki Bot

Bot Discord cho tra cứu Frame Data và Glossary của game đối kháng. Bot sử dụng
SQLite để lưu dữ liệu và hỗ trợ tìm gần đúng khi người dùng nhập sai tên.

## Yêu cầu

- Python 3.10 trở lên
- Một Discord application có Bot user
- Quyền `applications.commands` và `bot` khi mời bot vào server

## Cài đặt

Chạy các lệnh sau từ thư mục gốc của project:

```bash
python -m venv .venv
```

Kích hoạt virtual environment:

```powershell
.venv\Scripts\Activate.ps1
```

Hoặc trên macOS/Linux:

```bash
source .venv/bin/activate
```

Cài dependencies:

```bash
python -m pip install -r requirements.txt
```

## Cấu hình môi trường

Tạo file `.env` ở thư mục gốc:

```env
DISCORD_TOKEN=your_bot_token_here
DISCORD_GUILD_ID=123456789012345678
```

- `DISCORD_TOKEN`: token của Bot user, lấy trong **Discord Developer Portal >
  Bot > Token**. Không commit hoặc chia sẻ giá trị này.
- `DISCORD_GUILD_ID`: ID server dùng để sync slash command nhanh khi phát triển.
  Có thể để `0` hoặc bỏ trống để sync global command.

Để lấy server ID, bật **Developer Mode** trong Discord, sau đó nhấp phải vào
server và chọn **Copy Server ID**.

## Tạo và nạp database

Khởi tạo schema SQLite:

```bash
python -c "from utils.db import init_db; init_db()"
```

Database được tạo tại `data/database/wiki.db`. Để nạp dữ liệu, đặt một hoặc
nhiều file `.json` vào `data/raw/`, rồi chạy:

```bash
python -m utils.import_data
```

Mỗi file JSON có thể chứa một hoặc nhiều nhóm `characters`, `moves`,
`glossary`. Ví dụ:

```json
{
	"characters": [
		{
			"name": "Ryu",
			"display_name": "Ryu",
			"aliases": ["リュウ"]
		}
	],
	"moves": [
		{
			"character": "Ryu",
			"moves": [
				{
					"name": "Hadoken",
					"aliases": ["QCF+P"],
					"type": "special",
					"startup": 13,
					"active": 2,
					"recovery": 20,
					"on_hit": 2,
					"on_block": -6,
					"damage": 60,
					"guard": "Low, Air Unblockable",
					"adv_on_block": "-3",
					"adv_on_hit": "0",
					"invulnerability": "None",
					"image_url": "https://example.com/hadoken.png",
					"notes": "Projectile",
					"frame_notes": "Khoảng cách ảnh hưởng frame block."
				}
			]
		}
	],
	"glossary": [
		{
			"term": "Meaty",
			"category": "pressure",
			"definition": "Đòn đánh chạm đối thủ ở frame muộn của active window.",
			"aliases": ["meaty attack"]
		}
	]
}
```

Các key bắt buộc là `name` của character/move, cùng `term` và `definition`
của glossary. Các key còn lại có giá trị mặc định hợp lý nếu bị bỏ qua.

## Chạy bot

Từ thư mục gốc, sau khi đã tạo `.env` và database:

```bash
python -m app.bot
```

Khi chạy thành công, terminal sẽ in tài khoản bot và thông báo slash command
đã được sync. Nếu bot không phản hồi, kiểm tra token, server ID và quyền
`applications.commands` của bot.

## Slash commands

### `/frame character move`

Tra cứu startup, on hit, on block, damage và ghi chú của một chiêu thức. Hai
tham số có autocomplete; bot cũng thử fuzzy matching nếu không tìm thấy kết
quả chính xác.

### `/glossary term`

Tra cứu định nghĩa, phân loại và alias của một thuật ngữ. Tham số `term` có
autocomplete và fuzzy matching.

### `/add character name`

Mở form để thêm nhân vật. Lệnh yêu cầu quyền **Manage Server**; tên hiển thị
và alias là tùy chọn.

### `/add move character name image`

Mở form để thêm chiêu thức cùng startup, on hit, on block, damage và ghi chú.
Nhân vật phải tồn tại trước và người dùng cần quyền **Manage Server**.
Các trường frame data có thể để trống nếu chưa có thông tin. Tham số `image`
là tùy chọn; đính kèm ảnh trực tiếp khi gọi lệnh để bot hiển thị ảnh đó trong
`/frame`.

## Cấu trúc project

```text
app/                 Điểm vào và cấu hình bot
cogs/                Slash commands theo mô hình Discord.py Cog
data/schema.sql      Schema SQLite
data/raw/            Các file JSON nguồn để import
data/database/       Database SQLite được tạo khi khởi tạo
utils/db.py          Kết nối và khởi tạo database
utils/fuzzy.py       Tìm kiếm gần đúng
utils/import_data.py Import JSON vào SQLite
```

## Lưu ý

- Không đưa `.env`, token Discord hoặc `data/database/wiki.db` lên repository.
- Sau khi sửa dữ liệu JSON, chạy lại lệnh import để cập nhật database.
- Khi dùng `DISCORD_GUILD_ID`, command thường xuất hiện nhanh hơn. Sync global
  command có thể mất thời gian để Discord cập nhật.
