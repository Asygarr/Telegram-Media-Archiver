# tgdl — Telegram Protected Media Downloader

Mengunduh media (foto, video, dokumen, audio, voice, video note) dari grup/channel Telegram
dengan proteksi konten (`noforwards` / *Restrict Saving Content*) menggunakan **akun user MTProto**.

> ⚠️ **Gunakan secara sah.** Hanya untuk konten yang **berhak Anda akses** sebagai anggota grup/channel,
> untuk **arsip/penggunaan pribadi**. Patuhi Telegram Terms of Service, hak cipta, dan privasi.
> **Jangan pernah** meng-commit kredensial (`API_ID`, `API_HASH`, session string, nomor telepon).

---

## 1. Prasyarat
- **Python 3.11+** — cek dengan `python --version`.
- **pip** & **venv** (biasanya sudah termasuk Python).
- Akun **Telegram** aktif (Anda harus menjadi anggota grup/channel target).
- (Opsional) **git** untuk version control.

---

## 2. Instalasi Tools

### a. Masuk ke folder proyek
```bash
cd "telegram-downloader"
```

### b. Buat & aktifkan virtual environment
```bash
python -m venv .venv

# Windows (PowerShell / CMD):
.venv\Scripts\activate

# Linux / macOS:
source .venv/bin/activate
```

### c. Instal dependency (mode editable + dev)
```bash
pip install -U pip
pip install -e ".[dev]"
```

Ini memasang: `kurigram` (fork Pyrogram yang aktif & kompatibel dengan Python baru),
`python-dotenv`, `pydantic-settings`, `typer`, `rich` (runtime) serta `pytest`, `pytest-asyncio`,
`ruff`, `mypy` (pengembangan).

> **Akselerasi opsional (`tgcrypto`)** — mempercepat enkripsi. Instal bila wheel tersedia untuk versi
> Python Anda:
> ```bash
> python -m pip install -e ".[dev,speed]"
> ```
> Jika gagal build (mis. di Python paling baru), lewati saja — aplikasi tetap jalan, hanya sedikit
> lebih lambat (muncul peringatan "TgCrypto is missing").

> **Alternatif cepat (uv):**
> ```bash
> uv venv && uv pip install -e ".[dev]"
> ```

> **Catatan versi Python:** gunakan **Python 3.11–3.14**. Proyek memakai `kurigram` agar kompatibel
> dengan Python terbaru (Pyrogram asli error di Python 3.14).

### d. Verifikasi
```bash
tgdl --help
```

---

## 3. Mendapatkan API Telegram (`API_ID` & `API_HASH`)

Kredensial ini dibutuhkan agar aplikasi bisa terhubung ke Telegram sebagai akun user (MTProto).

### Langkah demi langkah
1. Buka **https://my.telegram.org** di browser.
2. Login dengan **nomor telepon Telegram** Anda → masukkan **kode login** yang dikirim ke aplikasi Telegram.
3. Klik menu **"API development tools"**.
4. Isi formulir **"Create new application"**:

   | Field | Isikan | Keterangan |
   |-------|--------|------------|
   | **App title** | `tgdl` (bebas) | Nama aplikasi, mis. `tgdl` atau `Media Archiver`. |
   | **Short name** | `tgdl` (bebas) | 5–32 karakter, huruf/angka. |
   | **URL** | *boleh dikosongkan* | Tidak wajib. Jika form menolak kosong, isi apa saja, mis. `https://example.com`. |
   | **Platform** | **Desktop** | Pilih **Desktop** (paling sesuai untuk skrip Python). Android/iOS/Web juga bisa — pilihan ini **tidak** membatasi penggunaan API. |
   | **Description** | bebas / kosong | Mis. `Personal media archiver`. Tidak berpengaruh teknis. |

5. Klik **"Create application"**.
6. Halaman menampilkan:
   - **`api_id`** — berupa **angka** (mis. `1234567`).
   - **`api_hash`** — berupa **string hex** (mis. `abcdef0123456789abcdef0123456789`).
7. **Catat dan rahasiakan** keduanya. Jangan bagikan atau commit ke repo.

> **Ringkasan pertanyaan umum:**
> - **Platform mana?** → **Desktop** (rekomendasi). Pilihan platform hanya label; tidak membatasi API.
> - **URL diisi apa?** → **Boleh dikosongkan**. Kalau wajib, isi `https://example.com`.
> - **Description diisi apa?** → **Bebas** (mis. `Personal media archiver`) atau dikosongkan.

---

## 4. Konfigurasi

Salin template lalu isi kredensial:
```bash
cp .env.example .env      # Windows: copy .env.example .env
```

Edit `.env`:
```dotenv
API_ID=1234567                 # dari my.telegram.org (WAJIB)
API_HASH=abcdef0123...         # dari my.telegram.org (WAJIB)
PHONE_NUMBER=+62812xxxxxxx     # untuk login pertama (opsional bila pakai SESSION_STRING)
SESSION_STRING=                # diisi setelah login pertama (langkah 5)
DOWNLOAD_DIR=downloads         # folder output
CONCURRENCY=3                  # jumlah unduhan paralel
LOG_LEVEL=INFO                 # DEBUG/INFO/WARNING/ERROR
```

> `.env` dan file session sudah masuk `.gitignore` — **tidak akan** ikut ter-commit.

---

## 5. Login & Session String (sekali saja)

Login pertama menghasilkan **session string** agar tidak perlu OTP setiap kali jalan:
```bash
python scripts/export_session.py
```
- Masukkan **nomor telepon**, **kode OTP**, dan **password 2FA** (bila akun mengaktifkannya).
- Salin **`SESSION_STRING`** yang tercetak ke `.env`.

> Session string setara kredensial penuh akun — perlakukan seperti password. Jika bocor, cabut dari
> Telegram → **Settings → Devices**.

---

## 6. Penggunaan

```bash
# Info chat + hitung kandidat media (tanpa unduh)
tgdl info @nama_grup

# Cek dulu tanpa mengunduh
tgdl download @nama_grup --dry-run

# Unduh semua media
tgdl download @nama_grup

# Hanya foto & video, maksimal 200 pesan, tulis metadata sidecar
tgdl download -1001234567890 --types photo,video --limit 200 --sidecar

# Lanjut dari message id tertentu, 5 unduhan paralel
tgdl download @channel --max-id 5000 --concurrency 5

# Hanya pesan dari Juni 2026 dengan caption mengandung "liburan"
tgdl download @channel --since 2026-06-01 --until 2026-06-30 --caption-contains liburan

# Daftar dialog yang dapat diakses
tgdl list
```

### Opsi `download`
| Opsi | Default | Fungsi |
|------|---------|--------|
| `--types` | semua | Filter tipe: `photo,video,document,audio,voice,...` |
| `--limit` | 0 (semua) | Batas jumlah pesan |
| `--min-id` / `--max-id` | 0 | Rentang message id |
| `--since` / `--until` | - | Rentang tanggal (`YYYY-MM-DD` atau ISO 8601) |
| `--caption-contains` | - | Hanya pesan dengan caption mengandung teks ini |
| `--out` | `downloads` | Direktori output |
| `--concurrency` | 3 | Unduhan paralel |
| `--dry-run` | false | List tanpa mengunduh |
| `--overwrite` | false | Abaikan dedup |
| `--sidecar` | false | Tulis `<file>.json` metadata |
| `--log-level` | INFO | Level log |

Hasil tersimpan di `downloads/<chat>/<tipe>/<message_id>_<nama>`. Menjalankan ulang hanya mengunduh
media baru (dedup), dan proses yang terputus dapat dilanjutkan (resume).

---

## 7. Pengembangan & Kualitas
```bash
pytest -v            # jalankan test
ruff check src tests # lint
ruff format src tests
mypy src             # type check
```

---

## 8. Struktur Proyek
```
telegram-downloader/
├─ src/tgdl/          # kode aplikasi (config, client, auth, discovery,
│                     #   downloader, storage, ratelimit, cli, logging_conf)
├─ scripts/export_session.py
├─ tests/             # unit & integration test
├─ .env.example
├─ .gitignore
├─ pyproject.toml
└─ README.md
```

## Status Implementasi
Dikembangkan bertahap sesuai [plan/](plan/README.md). Fase selesai: **00–10**
(fondasi → auth → engine → CLI → storage → error handling → testing).
