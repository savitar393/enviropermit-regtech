# T1 — Fondasi penalaran kasus

> Pembaruan: KB aktif telah dipusatkan dalam `kb/enviropermit.ttl`, release v2/schema 1.1. Lihat [panduan terkini](KB_dengan_Protege.md). Rincian path dan hasil 46 tes di bawah adalah catatan implementasi v1 sebelum migrasi TTL.

Ruang lingkup T1 adalah menjalankan kontrak `infer(FactBundle, KBRelease) -> InferenceResult` dengan OWLAPI/HermiT dan satu rule SWRLAPI/Drools. Kasus A/B/U/M/I/X/D/C disalin ke `cases/regression/water_spike/`, bersama expected outcomes independen yang disalin dari hasil spike. Folder referensi tetap utuh. Ini reproduksi interpretasi slice spike, belum pemilihan hukum yang berlaku berdasarkan tanggal (T2) atau implementasi seluruh modul water/air (T4).

## Dari kebutuhan kasus ke model

| Kebutuhan kasus | Representasi dan alasan | Bukti perilaku |
|---|---|---|
| Satu proyek, alternatif terpisah, satu assessment atas satu snapshot | `Project → hasScenario → Scenario`; `Assessment → assessesScenario/hasSnapshot`; qualified exact cardinality 1 | Dua snapshot yang dinyatakan berbeda membuat ontology tidak konsisten |
| Kegiatan air limbah adalah pendukung | `WaterActivity ⊑ SupportingActivity ⊑ Activity` | HermiT menghasilkan superclass yang tidak diassert |
| Perubahan desain pengolahan adalah perubahan teknis | `hasWaterTechnicalChange ⊑ hasTechnicalChange` | Mutasi penghapusan H menghilangkan kewajiban amendemen Pertek |
| Screening skenario berlaku untuk kegiatan yang berada di dalamnya | `hasActivity inverseOf isActivityOf` | Inverse membership dihasilkan tanpa input dua arah |
| Kewajiban kegiatan ikut menjadi kewajiban proyek | `hasActivity ∘ activityObligation ⊑ scenarioObligation`; `hasScenario ∘ scenarioObligation ⊑ projectObligation` | Triple proyek `projectObligation water_slo_required` tidak ada di input, ada di keluaran HermiT |
| Perubahan identitas tidak meniadakan penambahan kapasitas | Kelas perubahan disjoint; jalur tanpa dokumen baru memakai some + only | X tetap membutuhkan dokumen baru; I memakai jalur sempit |
| Klaim daftar perubahan lengkap harus eksplisit | Closure `hasProjectChange only {c1,…,cn}` hanya dari `changes_complete` dengan ID bukti | Inventaris parsial tidak membuktikan perubahan identitas saja |
| Luas sebaran dampak berubah/tidak berubah adalah temuan input | Data property fungsional `extentChanges` bertipe boolean; kelas cabang disjoint | A=true, B=false, U=tidak ada nilai, C=true+false konflik |
| Kandidat lampiran belum berarti pemenuhan kewajiban | `ObligationCandidate` mempunyai assessment, subjek, dan scope; SWRL menandai kandidat untuk review | Klasifikasi kandidat tidak menghasilkan `SATISFIED` atau penerbitan persetujuan |
| Urutan pengajuan berbeda dari penerbitan | Empat `StepKind`, edge yang diwarisi dari spike | UKL memiliki urutan pengajuan; AMDAL tidak mendapat urutan UKL |

`requiresStep` dideklarasikan transitif sebagai kosakata dependency. T1 belum membangun planner atau melakukan closure atas alternatif OR; pekerjaan itu berada di T6. Properti hasil chain/transitif tidak dipakai pada cardinality. Pengujian profile negatif sengaja melanggar syarat simple property dan harus ditolak OWLAPI.

## Kontrak dan isolasi

`CaseSnapshot` menyimpan konteks `(assessment_id, scenario_id, evidence_snapshot_id, assessed_on, kb_release_id)`, tujuan, periode, lokasi opsional, kegiatan, perubahan, temuan, dan pernyataan kelengkapan. Setiap temuan memiliki subjek, scope/outlet, periode, konteks, serta asal `HYPOTHETICAL`, `OBSERVED`, atau `EXPECTED_EFFECT`.

Adapter menolak penggunaan temuan yang konteks, subjek, outlet, atau periodenya berbeda. Expected effect hanya menjadi issue input; tidak masuk sebagai bukti. ABox memakai namespace hash seluruh konteks. Pemanggilan `infer` membuat proses JVM dan ontology manager baru; tidak menggunakan hasil inferensi sebelumnya. CLI langsung juga memvalidasi namespace, provenance, dan referensi individu. Pengujian ulang dengan ID individu yang sama membuktikan tidak ada cabang lama yang tertinggal.

`FactBundle` memuat asserted triples, provenance per fakta, named candidates, closure dengan ID bukti, normalized values (kosong pada slice boolean), dan issue input. Adapter tidak menambahkan kewajiban proyek, activityObligation, atau kelas hasil sebagai fakta input. `KBRelease` memin versi core/rule/query dengan SHA-256; file yang berubah tanpa manifest cocok ditolak. Release T1 bukan registry tanggal berlaku hukum.

Request CLI adalah `ReasoningRequest`; response adalah `InferenceResult`. Model JSON memakai field dan enum yang sama dengan model Python. Flag aturan harus boolean dan batas iterasi harus integer. Setiap assertion wajib memiliki tepat satu provenance yang berkonteks sama; indeks hilang/duplikat, asal tidak didukung, dan expected effect ditolak. Result selalu mengembalikan konteks penuh. Status konsistensi terpisah dari applicability dan fulfillment. U tetap `UNRESOLVED` pada `water_document_route` dengan `impact_extent_assessment`; kewajiban amendemen Pertek masih didukung secara entailment. Pemenuhan tetap `UNKNOWN`. Non-entailment tidak pernah diubah menjadi `NOT_APPLICABLE`.

## Urutan engine

1. Validasi request/release dan checksum, lalu profile check core OWLAPI `OWL2DLProfile`.
2. Tambahkan ABox/closure, profile check lagi, simpan `core-asserted.owl`.
3. HermiT memeriksa konsistensi dan mematerialisasikan entailment atas individu bernama; simpan `core-inferred.owl`.
4. Buat ontology rule **baru** berisi deklarasi dan fakta bernama hasil core. Muat `kb/rules/water-smoke.swrl` melalui parser SWRLAPI dan jalankan engine Drools.
5. Hanya head class allowlist pada kandidat yang telah disiapkan boleh dimaterialisasikan. Masukkan delta ke core tanpa rule SWRL, profile check dan konsistensi HermiT lagi. Ulangi sampai tidak ada fakta baru, maksimum 4 putaran (dapat diatur 1–16).
6. Simpan `swrl-delta.owl`, `final-inferred.owl`, `response.json`, request, dan log engine. Delta adalah fragmen fakta; profil dicek pada gabungannya dengan core. CLI menolak output yang akan menimpa hasil sebelumnya atau memakai nama file OWL tahap sebagai nama response.

Rule smoke mempunyai makna workflow: `TechnicalStudyBranch(a) ∧ hasStudyCandidate(a,c) → TechnicalStudyAttachmentCandidate(c)`. Head merupakan kandidat lampiran kajian teknis untuk review, berdasarkan cabang P5:16.1.a dari spike. Aksioma core kemudian mengklasifikasikannya sebagai `ReviewableCandidate`. Ini tidak mengklaim dokumen telah tersedia, diterbitkan, atau memenuhi persyaratan. Relasi persiapan kandidat diberi label `MODEL:candidate-workflow`.

Subset rule T1 sengaja terbatas pada class/object atoms dan satu head class yang diaudit: tidak ada built-in pembuat nilai/individu, negation-as-failure, atau penghapusan fakta. Record `fired_rules` menyimpan konsekuensi baru dari rule tunggal tersebut, bukan rekaman seluruh agenda internal Drools. Tahap gabungan tidak diklaim sebagai ontology SROIQ(D) yang decidable secara umum. Antarmuka SWRLAPI menjalankan impor, inferensi, dan ekspor fakta sesuai [dokumentasi engine resmi](https://github.com/protegeproject/swrlapi/wiki/SWRLRuleEngineAPI).

Ontology tidak konsisten, profile invalid, dan batas fixed point menghasilkan hasil karantina: tidak ada triples kesimpulan, klasifikasi, keputusan, atau kewajiban normal. T1 melaporkan konflik konteks ontology secara umum, belum minimal inconsistent subset/justification. Source traces adalah pemetaan kelas ke source ID yang diwarisi dari spike; penjelasan lengkap T8 belum diimplementasikan.

## Kompatibilitas dan reproduksi

Perintah lengkap tersedia di README root. Python 3.12.10, Maven 3.9.9, dan Java Temurin 21.0.12.1 dipakai dalam workspace ini. Library utama: OWLAPI **4.5.26**, HermiT **1.4.3.456**, SWRLAPI dan Drools adapter **2.1.3**, Drools **7.74.1.Final**, MVEL **2.5.2.Final**, Jackson **2.17.2**.

Parent SWRLAPI menyebut OWLAPI 4.5.27, tetapi parent POM versi itu tidak tersedia di Maven Central pada pengujian ini. Versi 4.5.26 dipilih setelah build. Dependency management memin MVEL 2.5.2.Final karena versi transitif 2.4.15.Final gagal dengan `java/lang/Compiler` pada Java 21, dan menyelaraskan Jackson karena OWLAPI menarik core/annotations lebih tua. Referensi pemilihan MVEL/Drools adalah [parent POM resmi SWRLAPI](https://github.com/protegeproject/swrlapi-parent/blob/master/pom.xml); keberhasilan yang diklaim harus didukung smoke test lokal, bukan hanya metadata versi.

## Bukti verifikasi

Verifikasi 15 November 2026 (Asia/Jakarta): `python scripts/verify.py --output artifacts/t1-final` menjalankan **46 tes lulus** dalam sekitar 4 menit 48 detik, lock 90 JAR cocok, dan core profile checker melaporkan **169 aksioma, 0 pelanggaran**. Log: `artifacts/t1-final/pytest.txt`; JUnit: `artifacts/t1-final/pytest.xml`; ringkasan yang dipertahankan untuk review: [T1-results.json](verification/T1-results.json).

| Kasus | Konsistensi | Kewajiban proyek | Jalur dokumen | Output SWRL |
|---|---|---:|---|---|
| A, extent berubah | CONSISTENT | 6 | TechnicalStudyBranch | 1 klasifikasi kandidat baru; HermiT menambahkan ReviewableCandidate |
| B, extent eksplisit tidak berubah | CONSISTENT | 6 | TechnicalStandardBranch | Tidak ada head smoke yang cocok |
| U, extent belum diketahui | CONSISTENT | 5 | **UNRESOLVED**, gap impact_extent_assessment | Tidak ada head smoke yang cocok |
| C, bukti true + false | **INCONSISTENT** | 0, karantina | Tidak diteruskan | Tidak dijalankan |

Seluruh core+ABox, termasuk C, lolos profile checker. Konsistensi adalah pemeriksaan terpisah: C valid secara profil OWL 2 DL tetapi tidak konsisten. A mempunyai 213 aksioma sebelum aturan dan 214 setelah satu fakta SWRL diterima; core murni tetap 169 aksioma.

Pada A, input tidak berisi triple kewajiban proyek. HermiT menghasilkan:

```text
project-food-project  projectObligation  water_slo_required
```

Nama subjek di atas disingkat; IRI lengkap dan konteksnya ada pada `artifacts/t1-final/A/request.json` dan `response.json`. Jalur entailment adalah kegiatan pembuangan permukaan pada skenario yang memiliki screening → `RegulatedSurfaceDischarge` → `activityObligation water_slo_required` → `scenarioObligation` → `projectObligation`. `project_slo_asserted=false` dan `project_slo_inferred_by_hermit=true` tercatat dalam ringkasan. Ini kewajiban untuk memiliki SLO pada kasus sintetis tersebut, bukan fakta bahwa SLO sudah diterbitkan atau harus selalu diterbitkan ulang.

Fakta SWRL tersimpan di `artifacts/t1-final/A/swrl-delta.owl`; klasifikasi setelah HermiT ada pada `final-inferred.owl`. Request/response setiap contoh, versi KB, asserted/core-inferred/final-inferred OWL, dan log engine berada dalam subdirektori A/B/U/C.

Tes juga mencakup dua snapshot berbeda yang dikonflikkan dengan cardinality satu, konteks baru dan ID individu yang dipakai ulang, bukti dari outlet/skenario/snapshot/assessment/tanggal/release/periode lain, expected effect, batas fixed point, checksum release, perubahan campuran, inventaris tidak lengkap, perbedaan pengajuan/penerbitan, serta mutasi H/chain/profile.

File utama untuk review: `src/enviropermit/contracts.py`, `inference.py`, `kb/core.owl`, `kb/rules/water-smoke.swrl`, `services/reasoner/src/main/java/id/enviropermit/`, dan kedua suite kontrak/regresi. Test profile dan mutasi berada di `tests/test_owl_profile.py`.
