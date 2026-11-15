# EnviroPermit-KBS — hasil uji kelayakan topik

**Tanggal:** 14 November 2026, Asia/Jakarta.  
**Keputusan:** GO untuk proyek dengan lingkup terbatas pada penalaran perubahan persetujuan lingkungan dan persetujuan teknis air limbah. Desain luas yang mencakup seluruh jenis perizinan belum tervalidasi.  
**Bentuk pengujian:** prototipe OWL yang benar-benar dieksekusi, pemeriksaan sumber primer, pengujian perilaku, pemeriksaan profil OWL 2 DL, dan empat mutasi kesalahan. Ini bukan aplikasi produksi atau penetapan kewajiban proyek nyata.

## 1. Pertanyaan yang diuji

Apakah EnviroPermit mempunyai pengetahuan dan relasi yang cukup untuk menghasilkan keputusan kasus, menangani ketidaklengkapan, dan menyusun ketergantungan proses—sehingga layak menjadi proyek Knowledge Base and Reasoning yang serius?

Persyaratan berasal dari pembahasan proyek sebelumnya. PDF materi kuliah tidak digunakan sebagai project brief. Kekhususan Indonesia tidak diberi bonus dalam penilaian. Akses wawancara pakar tidak dijadikan prasyarat.

| Gerbang kelayakan | Bukti yang diperoleh | Penilaian |
|---|---|---|
| Dua keluarga aturan berinteraksi | Aturan perubahan persetujuan lingkungan digabung dengan aturan perubahan Pertek air limbah | Lulus pada lingkup uji |
| Kesimpulan relasional baru | Kewajiban di tingkat kasus diturunkan melalui kegiatan dan property chain; tidak diisi langsung | Lulus |
| Pengecualian atau kasus belum dapat diputuskan | Perubahan identitas saja, campuran perubahan identitas/kapasitas, inventaris belum lengkap, dampak belum diketahui, bukti konflik | Lulus pada kasus yang diuji |
| Dua alternatif | Dua skenario desain menghasilkan kebutuhan dokumen teknis berbeda | Lulus terbatas: alternatif disediakan, bukan ditemukan oleh planner |
| Penjelasan dengan sumber | Kelas hasil inferensi dipetakan ke ketentuan hukum dan asumsi pemodelan yang terpisah | Lulus terbatas: belum minimal justification dari reasoner |

## 2. Batas kasus

Kasus sintetis adalah fasilitas manufaktur yang sudah memiliki persetujuan lingkungan dan Pertek air limbah, dengan rencana perubahan produksi dan pengolahan air limbah yang dibuang langsung ke badan air permukaan.

Asumsi yang sengaja dinyatakan sebagai masukan:

- Jenis perubahan proyek sudah dipetakan secara benar, misalnya penambahan kapasitas atau perubahan identitas.
- AMDAL/UKL-UPL untuk konfigurasi yang diusulkan merupakan hasil penapisan yang disediakan. Dokumen lama tidak otomatis menentukan rezim proyek setelah perubahan.
- Penilaian apakah luas sebaran dampak berubah merupakan bukti teknis yang disediakan. Ontologi tidak menghitung dispersi pencemar.
- Status lengkap/tidak lengkap inventaris perubahan dinyatakan eksplisit.

Uji tidak mencakup air limbah domestik, industri pakan, emisi udara, pengecualian kawasan lindung, kewenangan penerbit, semua ambang KBLI, seluruh jalur outsourcing, atau penetapan dokumen AMDAL/addendum/UKL-UPL secara lengkap.

## 3. Pengetahuan yang berhasil diformalkan

**Keluarga A — perubahan persetujuan lingkungan.** PP 22/2021 Pasal 89–90 membedakan perubahan yang melalui jalur penyusunan dokumen lingkungan baru dan perubahan yang melalui jalur tanpa dokumen lingkungan baru. Penambahan kapasitas termasuk kelompok pertama; perubahan identitas termasuk kelompok kedua. Pasal 91 menjelaskan ragam dokumen pada jalur pertama. Model tidak menyamakan “dokumen baru” dengan “pasti AMDAL baru”, dan tidak menyamakan “tanpa dokumen lingkungan baru” dengan “tanpa administrasi”. [R1]

**Keluarga B — perubahan Pertek air limbah.** Permen LHK 5/2021 Pasal 15–16 mengatur perubahan teknis serta pemilihan kajian teknis atau dokumen pemenuhan standar teknis berdasarkan perubahan luas sebaran dampak. Tidak adanya bukti perubahan bukan bukti bahwa dampak tidak berubah. [R2]

**Interaksi.** Persyaratan Pertek memengaruhi proses persetujuan lingkungan. Pasal 8 membedakan urutan pengajuan pada jalur UKL-UPL dan AMDAL; Pasal 14 berkaitan dengan penerbitan persetujuan lingkungan; Pasal 16(2) menerapkan prosedur terkait pada perubahan Pertek. PP 22/2021 Pasal 93(2) juga menghubungkan perubahan pengelolaan/pemantauan dengan perubahan Pertek. Pengajuan dan penerbitan sengaja dimodelkan sebagai peristiwa berbeda. [R1–R2]

Status PP 22/2021 dan Permen LHK 5/2021 diperiksa pada sumber resmi. Permen LHK 5/2021 tercatat dicabut sebagian oleh Permen LH/BPLH 2/2026 untuk ketentuan tertentu pada usaha pakan. Ketentuan tersebut tidak dimasukkan dalam uji. Temuan ini menunjukkan bahwa versi harus dikelola per ketentuan dan lingkup, bukan sekadar satu label “berlaku” pada seluruh dokumen. Ini bukan audit lengkap semua perubahan regulasi terkait. [R3–R5]

## 4. Dua skenario dan kasus pembanding

Kedua alternatif A/B mempertahankan tujuan hipotetis penambahan kapasitas. Perbedaannya adalah hasil penilaian teknis atas rancangan pengolahan air limbah. Kelayakan rekayasa kedua desain diasumsikan untuk menguji konsekuensi aturan; tidak dilakukan simulasi fisik.

| Kasus | Fakta pembeda | Hasil eksekusi |
|---|---|---|
| A | Kapasitas naik; desain pengolahan berubah; luas sebaran dampak berubah | Perubahan persetujuan lingkungan; jalur dokumen lingkungan baru; perubahan Pertek; kajian teknis |
| B | Tujuan kapasitas sama; rancangan alternatif disertai bukti luas sebaran dampak tidak berubah | Kewajiban perubahan tetap; dokumen pemenuhan standar teknis menggantikan cabang kajian teknis |
| U | Penilaian luas sebaran dampak belum tersedia | Perubahan Pertek tetap terinferensi; jenis dokumen teknis belum dipilih; bukti diminta |
| M | Hanya perubahan pengelolaan/pemantauan yang dimodelkan; inventaris lengkap; pengelolaan air limbah berubah | Jalur tanpa dokumen lingkungan baru dapat terinferensi, tetapi perubahan Pertek dan ketergantungannya tetap ada |
| I | Hanya perubahan identitas; inventaris lengkap; tidak ada perubahan teknis yang dinyatakan | Perubahan persetujuan lingkungan tetap diperlukan; jalur tanpa dokumen lingkungan baru; tidak muncul kesimpulan perubahan Pertek |
| X | Perubahan identitas bersama penambahan kapasitas | Jalur dokumen lingkungan baru tetap berlaku; cabang identitas-saja tidak terinferensi |
| D | Penapisan konfigurasi yang diusulkan menyatakan AMDAL | Tidak dipaksakan aturan pengajuan Pertek harus selalu lebih dahulu seperti pada UKL-UPL; pengajuan bersamaan dikenali |
| C | Penilaian yang sama menyatakan luas dampak berubah dan tidak berubah | Ontologi kasus tidak konsisten; keluaran kewajiban ditahan |

“Tidak terinferensi” tidak berarti “secara hukum pasti tidak wajib”. Kewajiban mempunyai SLO juga tidak berarti harus mengajukan SLO baru dalam setiap perubahan; pemenuhan atau keberlakuan SLO yang ada belum dievaluasi.

## 5. Hasil teknis yang benar-benar dijalankan

| Pemeriksaan | Hasil teramati |
|---|---|
| Pengujian perilaku | 16/16 lulus; keluaran lengkap di `test_output.txt` |
| Baseline sebelum aturan dibuat | 16/16 ekspektasi gagal sebagai assertion failure, bukan import/runtime error |
| Pemeriksaan OWLAPI OWL2DLProfile | 8/8 berkas ontologi contoh berada dalam profil OWL 2 DL; nol pelanggaran |
| Mutasi property chain dihapus | Pengujian kewajiban hasil propagasi gagal sebagaimana diharapkan |
| Mutasi hierarki properti dihapus | Pengujian interaksi perubahan teknis gagal sebagaimana diharapkan |
| Mutasi inventaris tidak lengkap dianggap lengkap | Pengujian pengecualian identitas-saja menangkap kesalahan |
| Mutasi dampak tidak diketahui dianggap tidak berubah | Pengujian ketidaklengkapan menangkap kesalahan |

Keempat mutasi terdeteksi melalui kegagalan perilaku, tanpa runtime error. Ini memperkuat bukti bahwa pengujian peka terhadap kesalahan yang relevan, bukan hanya membaca ulang teks aturan.

Lingkungan eksekusi: Python 3.12, Owlready2 0.51, HermiT bawaan Owlready2, RDFLib 7.6.0, JPype1 1.7.1, OpenJDK 21.0.13. Tidak menggunakan LLM untuk menghasilkan keputusan kasus.

Profil OWL 2 DL dan konsistensi adalah dua pemeriksaan berbeda. Kasus C sengaja tidak konsisten tetapi masih merupakan ontologi yang sah secara profil. Kasus dengan dua snapshot yang dinyatakan berbeda juga ditolak karena kontrak tepat satu snapshot per penilaian.

## 6. Kontribusi ontology dan kode biasa

| Bagian | Peran yang dijalankan |
|---|---|
| TBox | Mendefinisikan cabang perubahan lingkungan, kegiatan pembuangan yang diatur, perubahan teknis, dan kebutuhan dokumen |
| RBox | Subproperty `hasWaterTechnicalChange` → `hasTechnicalChange`; inverse kegiatan/kasus; chain `hasActivity` + `activityObligation` → `caseObligation` |
| ABox | Fakta hipotetis satu kasus dan snapshot, perubahan yang diusulkan, hasil penapisan, bukti teknis |
| HermiT | Menginferensikan kelas, kewajiban, relasi, dan mendeteksi inkonsistensi |
| Python | Memasukkan fakta, menjalankan reasoner, menampilkan hasil, dan meminta bukti yang belum tersedia |

Nominal digunakan untuk kategori kewajiban/penapisan dan penutupan inventaris yang eksplisit; inverse untuk hubungan kegiatan dengan kasus; qualified cardinality untuk satu snapshot; datatype boolean untuk hasil penilaian dampak; existential/universal restrictions untuk syarat dan kelengkapan. Property chain tidak diberi pembatasan kardinalitas yang melanggar persyaratan simple-property OWL 2 DL. [R6]

Belum ada SWRL, transitive prerequisite closure, SHACL, antarmuka pengguna, atau planner pencari alternatif. Lulus profil OWL 2 DL tidak otomatis membuktikan semua target penggunaan SROIQ(D) dalam proyek akhir terpenuhi. Persentase 80% KBR juga belum diukur; angka itu tidak dapat diturunkan dari jumlah kelas, aturan, atau baris kode.

## 7. Arti hasil terhadap pemilihan proyek

**Alasan melanjutkan:** sumber dapat diturunkan menjadi aturan eksplisit; terdapat interaksi kewajiban dan ketergantungan proses; ontology menghasilkan relasi baru; ketidaklengkapan dan konflik mempunyai konsekuensi nyata. Topik ini layak dikembangkan melampaui pencarian KBLI atau daftar dokumen.

**Batas yang mengurangi kekuatannya:** sebagian antecedent penting masih merupakan hasil penilaian yang diberikan dari luar. Dua alternatif belum ditemukan atau dioptimalkan oleh sistem. Graph proses baru memuat ketergantungan yang diuji, belum prosedur lengkap. Penjelasan adalah pemetaan kelas hasil inferensi ke sumber, bukan proof extraction otomatis. Kasus dan interpretasi dibuat dalam sesi yang sama, sehingga ini bukan validasi hukum independen atau akurasi pada kasus lapangan.

**Terhadap RecoverGraph:** EnviroPermit mempunyai dasar KBR yang nyata, tetapi belum menyamai kekuatan validasi empiris RecoverGraph. Pada RecoverGraph, hipotesis rencana dapat dibandingkan dengan hasil restore yang benar-benar dijalankan. Pada EnviroPermit, lulus reasoner hanya membuktikan kesesuaian dengan formalization yang dipilih; interpretasi dan kelengkapan aturan tetap harus diuji tersendiri.

**Terhadap AquaVet v2 dan NusaMangrove:** uji ini menguatkan alasan sementara memilih EnviroPermit untuk keterlacakan ketentuan dan pengujian logika. Belum ada eksperimen setara pada dua kandidat lain, jadi hasil ini tidak membuktikan peringkat komparatif secara empiris.

## 8. Lingkup proyek yang sekarang disarankan

**Judul kerja:** Sistem Pakar Berbasis Ontologi untuk Penalaran Perubahan Persetujuan Lingkungan dan Persetujuan Teknis Air Limbah.

Mulai dari satu subsektor manufaktur, persetujuan yang sudah ada, perubahan kapasitas/identitas/pengelolaan, dan pembuangan air limbah industri ke badan air permukaan. Bekukan sumber per ketentuan dan tanggal. Pertahankan penapisan serta hasil kajian dampak sebagai bukti yang harus ditelusuri asalnya sampai modul penalarannya memang dibangun.

Urutan pengembangan berikut yang masuk akal:

1. Buat matriks ketentuan–syarat–pengecualian–bukti–output, termasuk aturan terkait yang belum terwakili.
2. Tambahkan pemilihan jalur dokumen lingkungan secara teruji, dengan ambang, lokasi, dokumen awal, dan versi regulasi dalam lingkup yang dibatasi.
3. Bangun graph tindakan per kasus dengan prasyarat, status terpenuhi/belum diketahui, dan propagasi ketergantungan. Jangan menyatukan langkah dari dua skenario.
4. Bandingkan alternatif yang disediakan dengan alasan perubahan keputusan. Jangan memberi label “terbaik” sebelum tujuan perbandingan dan bukti kelayakannya jelas.
5. Bekukan kumpulan kasus evaluasi dari sumber resmi yang dipisahkan dari kasus pengembangan, termasuk batas ambang, pengecualian, perubahan campuran, bukti konflik, dan perubahan versi.

Keseluruhan langkah ini dapat dikerjakan berbasis referensi. Reviewer manusia bersifat tambahan; yang wajib adalah sumber yang jelas, interpretasi transparan, dan pengujian yang tidak menganggap kode sendiri sebagai kebenaran hukum.

## Referensi

- **R1.** Pemerintah RI. PP 22/2021, terutama Pasal 89–94. [Naskah resmi](https://jdih.kemenkoinfra.go.id/cfind/source/files/pp/2021/1.-salinan-pp-nomor-22-tahun-2021.pdf).
- **R2.** KLHK. Permen LHK 5/2021, terutama Pasal 3, 8, 14–17. [Naskah resmi](https://jdih.menlhk.go.id/new/uploads/files/2021pmlhk005_menlhk_06082021104129.pdf).
- **R3.** JDIH BPK. [Status PP 22/2021](https://peraturan.bpk.go.id/Details/161852/pp-no-22-tahun-2021).
- **R4.** JDIH BPK. [Status Permen LHK 5/2021 dan pencabutan sebagian](https://peraturan.bpk.go.id/Details/210999/).
- **R5.** JDIH BPK. [Permen LH/BPLH 2/2026](https://peraturan.bpk.go.id/Details/347119/permen-lhbplh-no-2-tahun-2026).
- **R6.** W3C. [OWL 2 Structural Specification and Functional-Style Syntax](https://www.w3.org/TR/owl2-syntax/).
- **R7.** Owlready2. [Reasoning documentation, versi 0.51](https://owlready2.readthedocs.io/en/v0.51/reasoning.html).

Paket pendamping memuat kode, ontologi sebelum/sesudah inferensi, masukan kasus, hasil pengujian, hasil mutasi, hasil profile checker, dan peta sumber.
