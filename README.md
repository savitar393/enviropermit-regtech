# EnviroPermit-KBS

**KB aktif: [`kb/enviropermit.ttl`](kb/enviropermit.ttl)** — satu file OWL + SWRL yang dapat diedit di Protégé. Baca [panduan Protégé](docs/KB_dengan_Protege.md).

T1: model kasus dengan cakupan snapshot, core OWL 2 DL, HermiT, dan tahap SWRLAPI/Drools terpisah. Contoh pertama mempertahankan kasus sintetis air limbah dari spike. Modul regulasi lengkap, registry versi hukum, planner, API, dan UI mengikuti task berikutnya.

Gunakan Python 3.12 dan Java 21; Maven 3.9.9. Versi library yang benar-benar diuji dicatat dalam `pyproject.toml`, `requirements.lock.txt`, `services/reasoner/pom.xml`, dan `services/reasoner/dependencies.lock.json`. Workspace ini sudah mempunyai `.venv` dan Maven lokal; perintah tes/CLI dapat langsung dijalankan. Blok persiapan berikut untuk environment baru dengan Python/Maven yang terpasang.

```powershell
# Dari D:\EnviroPermit; Maven dan Java tersedia di PATH.
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock.txt
.venv/Scripts/python.exe -m pip install --no-deps -e .
mvn -f services/reasoner/pom.xml package

# Jika menggunakan tool lokal yang sudah disiapkan dalam workspace ini:
./scripts/build_reasoner.ps1

.venv/Scripts/python.exe -m pytest tests/test_reasoner_contract.py tests/regression -q
.venv/Scripts/python.exe -m enviropermit.cli --case cases/regression/water_spike/A.json --output artifacts/demo-A
.venv/Scripts/python.exe -m enviropermit.cli --case cases/regression/water_spike/U.json --output artifacts/demo-U
.venv/Scripts/python.exe scripts/verify.py --output artifacts/verification-new
```

Setiap direktori output harus baru/kosong. `verify.py` memeriksa lock dependency, menjalankan **seluruh** tes, profile checker OWLAPI, dan ekspor A/B/U/C. Log Maven “No tests to run” hanya berarti tes Java tidak berada di Surefire: suite integrasi Python memanggil CLI Java/HermiT/Drools yang sebenarnya.

CLI langsung memakai JSON request/response yang sama dengan adapter:

```powershell
$cp = 'services/reasoner/target/classes;services/reasoner/target/dependency/*'
New-Item -ItemType Directory -Path artifacts/direct-A
java -cp $cp id.enviropermit.ReasoningCli infer artifacts/demo-A/request.json artifacts/direct-A/response.json
java -cp $cp id.enviropermit.ReasoningCli profile kb/enviropermit.ttl artifacts/core-profile.json
```

Exit code Python CLI: `0` konsisten, `2` konflik/profile invalid/tidak konvergen. CLI Java menulis status reasoning dalam JSON; exit `1` berarti kesalahan request/engine, dan perintah `profile` mengembalikan `2` untuk profile invalid.

Lihat [kontrak, keputusan pemodelan, dan bukti T1](docs/T1_reasoning.md), [rencana proyek](docs/EnviroPermit_KBS_Project_Plan.md), serta [README spike asli](reference/spike/EnviroPermit_KBS_Test/README.md).
