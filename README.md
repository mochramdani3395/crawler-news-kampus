# Suteki News Radar (URL Harvester & AI Radar)

Automasi pengumpul URL berita dan isu terkini seputar ekosistem **Perguruan Tinggi di Indonesia** (SIAKAD Cloud, Neo Feeder PDDIKTI, Akreditasi BAN-PT/LAM, SPMI, Regulasi Kemdiktisaintek, Portal Resmi LLDIKTI, PMB) berbasis **GitHub Actions** yang langsung disinkronkan ke **Google Sheets** dengan arsitektur **Two-Tier AI Scoring**.

---

## 🚀 Sumber Ingesti Berita & Pengumuman Resmi

Pipeline secara otomatis memantau 3 kanal sumber:
1. **Google News RSS Search**: Kata kunci terfokus (SIAKAD, Neo Feeder, PDDIKTI, Akreditasi Kampus, BAN-PT, LAM-INFOKOM, LAMDIK, SPMI, Kemdiktisaintek, LLDIKTI, Server Kampus Down, PMB).
2. **Media Edukasi & RSS Resmi**: Antara Humaniora, Sindonews Edukasi, RSS LLDIKTI 3 & LLDIKTI 4.
3. **Web Portal Resmi LLDIKTI (Direct HTML Scraper)**:
   - **LLDIKTI Wilayah 3 (Jakarta)**:
     - `https://lldikti3.kemdiktisaintek.go.id/pengumuman/` (Surat Edaran, BKD, Evaluasi Layanan)
     - `https://lldikti3.kemdiktisaintek.go.id/berita-lldikti/` (Bimtek Tracer Study, Mutu, SINTA)
     - `https://lldikti3.kemdiktisaintek.go.id/berita-perguruan-tinggi/` (Kabar PTS binaan)
   - **LLDIKTI Wilayah 4 (Jabar & Banten)**:
     - `https://lldikti4.kemdiktisaintek.go.id/info-lldikti-wilayah-iv/` (Pelaporan PDDIKTI, Akreditasi LAMSAMA, Info Regulasi)

---

## ⚙️ Alur Kerja Sistem (Two-Tier AI Scoring)

```text
[ GitHub Actions (Cron 06:00 WIB / Manual Trigger) ]
                       │
                       ▼
         [ Python Engine (harvester.py) ]
  - Menarik Google News RSS & Portal Edukasi Nasional
  - Menarik Web Portal Resmi LLDIKTI 3 & LLDIKTI 4 (Pengumuman & Berita)
  - Ekstraksi Tanggal Terbit Asli (WIB) & Tanggal Crawl
  - Ekstraksi Cuplikan Berita (1 paragraf ringkasan)
  - Anti-duplikasi URL otomatis berbasis Google Sheet
                       │
                       ▼
        [ Tier 1: Gemini Free Triage ]
  - Auto-fallback multi-model Flash (3.5-flash / 3.8-flash / 3.1-flash-lite)
  - Triage cepat skala 1-10, catatan alasan awal, & intisari cuplikan
  - Surat edaran & pengumuman LLDIKTI diprioritaskan (Skor 8-10)
                       │
                       ▼
        [ Google Sheets ('News_Radar') ]
  - Tersinkronisasi rapi dalam skema 12 kolom
  - Kolom editorial disiapkan untuk review mendalam
                       │
                       ▼
        [ Tier 2: ChatGPT Web / Suteki Content Engine ]
  - Deep-dive analisis editorial & rekomendasi angle
  - Produksi artikel resmi blog Suteki, GDocs, & ClickUp
```

---

## ⚙️ Konfigurasi Repository Secrets di GitHub

Di menu **GitHub Repository $\rightarrow$ Settings $\rightarrow$ Secrets and variables $\rightarrow$ Actions**:

1. **`SPREADSHEET_ID`**: ID Google Spreadsheet (dari URL `/d/{SPREADSHEET_ID}/edit`).
2. **`GCP_SA_KEY`**: Isi lengkap file JSON kredensial Service Account Google Cloud.
   *Penting:* Pastikan email bot Service Account (`client_email`) telah diundang ke Google Spreadsheet sebagai **Editor**.
3. **`GEMINI_API_KEY`**: API Key gratis dari [Google AI Studio](https://aistudio.google.com/).

---

## 🤖 Menjalankan Manual (Uji Coba / Backfill)

Selain berjalan otomatis setiap hari pukul **06:00 WIB**, Anda bisa memicu penarikan data kapan saja:
1. Buka tab **Actions** di repositori GitHub ini.
2. Pilih workflow **Suteki News Radar Harvester**.
3. Klik tombol **Run workflow** $\rightarrow$ **Run workflow**.

---

## 📝 Format Kolom di Google Sheets (12 Kolom)

| Kolom | Header | Keterangan |
| :---: | :--- | :--- |
| **A** | `Tanggal Terbit` | Waktu posting aktual artikel rilis (YYYY-MM-DD HH:MM WIB) |
| **B** | `Tanggal Crawl` | Tanggal saat bot menarik data artikel ini (YYYY-MM-DD) |
| **C** | `Sumber Media` | Portal berita / Web LLDIKTI (LLDIKTI 3 - Pengumuman, LLDIKTI 4, Antara, dll) |
| **D** | `Judul Berita` | Judul artikel berita yang sudah dibersihkan |
| **E** | `Cuplikan Berita` | 1 paragraf pendek / ringkasan intisari isi berita |
| **F** | `URL Berita` | Link artikel asli (Kunci anti-duplikasi & riset ChatGPT) |
| **G** | `Kata Kunci Terdeteksi` | Kategori (SIAKAD, PDDIKTI, Akreditasi, Regulasi, PMB) |
| **H** | `Skor Awal Bot (1-10)` | **Tier 1**: Scoring triage otomatis oleh Gemini |
| **I** | `Catatan Awal Bot` | **Tier 1**: Alasan singkat penilaian relevansi Suteki |
| **J** | `Skor Final Editorial` | **Tier 2**: Review mendalam oleh ChatGPT / Redaksi |
| **K** | `Rekomendasi Angle Suteki`| **Tier 2**: Usulan sudut pandang konten blog Suteki |
| **L** | `Status Tindak Lanjut` | Antrean / Siap Tulis / Diterbitkan / Abaikan |
