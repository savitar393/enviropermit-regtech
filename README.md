# EnviroPermit-KBS

EnviroPermit-KBS adalah prototipe sistem pendukung keputusan untuk menilai kewajiban lingkungan dari kegiatan dan perubahan suatu proyek. Contoh yang dapat dijalankan saat ini menggunakan kasus sintetis perubahan pengelolaan air limbah.

**Status pengembangan.** Tahap T1–T3 menyediakan model kasus, registry sumber dan pemilihan versi ketentuan berdasarkan tanggal/lingkup, penapisan dokumen lingkungan (`AMDAL`/`UKL-UPL`/`SPPL`) berbasis kapasitas dan kawasan lindung beserta perambatan perubahan proyek, CLI, serta rangkaian tes penalaran. Kewajiban emisi, komposisi multiaktivitas, perencanaan, API, dan antarmuka web masih dalam rencana. [Rencana proyek](docs/EnviroPermit_KBS_Project_Plan.md)

## Menjalankan contoh

Gunakan Python 3.12, JDK 21, dan Maven 3.9.9. Jalankan perintah berikut dari root repositori di PowerShell.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
mvn -f services/reasoner/pom.xml package
```

```powershell
.\.venv\Scripts\python.exe -m enviropermit.cli --case cases/regression/water_spike/A.json --output artifacts/demo-A
.\.venv\Scripts\python.exe -m enviropermit.cli --case cases/regression/water_spike/U.json --output artifacts/demo-U
```

Pada kasus A, HermiT menurunkan kewajiban SLO proyek dari relasi kegiatan. Pada kasus U, jenis dokumen teknis tetap `UNRESOLVED` karena bukti mengenai perubahan luas sebaran dampak belum tersedia. Setiap perintah membutuhkan direktori output baru atau kosong. Hasil JSON tersimpan sebagai `response.json` di direktori tersebut.

## Basis pengetahuan

Aturan domain, aksioma OWL, aturan SWRL, dan kebutuhan bukti tersimpan dalam satu file Turtle yang bisa dibuka di Protégé. CLI menjalankan HermiT pada inti OWL 2 DL, lalu menjalankan aturan SWRL melalui Drools pada tahap terpisah. [Basis pengetahuan](kb/enviropermit.ttl) · [Panduan Protégé dan versi basis pengetahuan](docs/KB_dengan_Protege.md)

## Verifikasi

```powershell
.\.venv\Scripts\python.exe scripts/verify.py --output artifacts/verification
```

Verifikasi memeriksa versi dependensi Java, menjalankan tes, memeriksa profil OWL 2 DL, dan mengekspor hasil kasus regresi. [Ringkasan verifikasi T1](docs/verification/TTL-results.json)
