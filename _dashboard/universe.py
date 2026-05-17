"""Curated candidate universe of biotech-adjacent tickers with metadata.

Each ticker carries:
- a human-readable company name
- a 1-line blurb describing what the company actually does
- the biotechnology color categories it belongs to

Categorization follows the seven-color framework:
    Red    = medical / pharmaceutical
    Green  = agricultural (incl. animal health)
    White  = industrial (enzymes, biofuels, bioplastics)
    Blue   = marine / aquatic
    Grey   = environmental (bioremediation, water, recycling)
    Yellow = food / nutrition (fermentation, nutraceuticals)
    Gold   = bioinformatics / computational biology / AI-bio

A ticker can live in multiple categories when its business legitimately
spans them (e.g. AQB = Green + Blue, BTAI = Red + Gold).

Knowledge cutoff Jan 2026; tickers that yfinance can no longer resolve
are silently dropped by the live filter.
"""

from __future__ import annotations

from dataclasses import dataclass


RED    = "Red_Medical_Pharmaceutical"
GREEN  = "Green_Agricultural"
WHITE  = "White_Industrial"
BLUE   = "Blue_Marine"
GREY   = "Grey_Environmental"
YELLOW = "Yellow_Food_Nutrition"
GOLD   = "Gold_Bioinformatics"

FOLDERS = (RED, GREEN, WHITE, BLUE, GREY, YELLOW, GOLD)


@dataclass(frozen=True)
class CompanyInfo:
    name: str
    blurb: str
    categories: tuple[str, ...]


INFO: dict[str, CompanyInfo] = {
    # ---------- Red: medical / pharmaceutical ----------
    "APLT": CompanyInfo("Applied Therapeutics",  "Aldose-reductase inhibitors for galactosemia and diabetic complications.", (RED,)),
    "OCGN": CompanyInfo("Ocugen",                "Modifier-gene therapies and vaccines for retinal diseases.",                (RED,)),
    "INMB": CompanyInfo("INmune Bio",            "Innate-immunity modulators for cancer and Alzheimer's (XPro, INKmune).",     (RED,)),
    "ONCY": CompanyInfo("Oncolytics Biotech",    "Oncolytic-virus immunotherapy pelareorep for solid tumors.",                (RED,)),
    "SLNO": CompanyInfo("Soleno Therapeutics",   "DCCR (Vykat) for hyperphagia in Prader-Willi syndrome.",                    (RED,)),
    "FENC": CompanyInfo("Fennec Pharmaceuticals","PEDMARK to prevent cisplatin-induced ototoxicity in pediatric cancer.",     (RED,)),
    "CRMD": CompanyInfo("CorMedix",              "DefenCath antimicrobial catheter-lock solution for hemodialysis.",          (RED,)),
    "CYCC": CompanyInfo("Cyclacel Pharmaceuticals","Oncology kinase inhibitors (fadraciclib, plogosertib).",                  (RED,)),
    "KZIA": CompanyInfo("Kazia Therapeutics",    "Paxalisib (PI3K/mTOR) for glioblastoma and brain metastases.",              (RED,)),
    "SNGX": CompanyInfo("Soligenix",             "HyBryte for cutaneous T-cell lymphoma; rare-disease and vaccine platform.", (RED,)),
    "TENX": CompanyInfo("Tenax Therapeutics",    "Levosimendan for pulmonary hypertension with heart failure.",               (RED,)),
    "MNPR": CompanyInfo("Monopar Therapeutics",  "Radiopharmaceuticals and oncology candidates (MNPR-101, Validive).",        (RED,)),
    "PHIO": CompanyInfo("Phio Pharmaceuticals",  "INTASYL self-delivering RNAi for immuno-oncology.",                          (RED,)),
    "GRTS": CompanyInfo("Gritstone bio",         "Personalized-neoantigen mRNA cancer and HIV vaccines.",                     (RED,)),
    "CRBP": CompanyInfo("Corbus Pharmaceuticals","Antibody-drug conjugates and oncology biologics.",                          (RED,)),
    "NRBO": CompanyInfo("NeuroBo Pharmaceuticals","Cardiometabolic and CNS therapeutics (DA-1241, DA-1726).",                  (RED,)),
    "MIST": CompanyInfo("Milestone Pharmaceuticals","Etripamil nasal spray for paroxysmal SVT and atrial fibrillation.",     (RED,)),
    "ATAI": CompanyInfo("ATAI Life Sciences",    "Psychedelic and mental-health therapeutics platform.",                       (RED,)),
    "KPRX": CompanyInfo("Kiromic Biopharma",     "Allogeneic gamma-delta T-cell therapies for solid tumors.",                  (RED,)),
    "INM":  CompanyInfo("InMed Pharmaceuticals", "Rare-cannabinoid drug candidates for ocular and CNS disease.",               (RED,)),
    "VINC": CompanyInfo("Vincerx Pharma",        "Bioconjugation oncology platform (enitociclib, VIP236).",                    (RED,)),
    "HEPA": CompanyInfo("Hepion Pharmaceuticals","Rencofilstat (cyclophilin inhibitor) for NASH and liver disease.",          (RED,)),
    "ATXI": CompanyInfo("Avenue Therapeutics",   "CNS-pain pipeline including IV tramadol and AJ201 for SBMA.",                (RED,)),
    "ABOS": CompanyInfo("Acumen Pharmaceuticals","Sabirnetug, an Aβ-oligomer antibody for early Alzheimer's.",                 (RED,)),
    "VYNE": CompanyInfo("VYNE Therapeutics",     "Topical BET inhibitors for immuno-inflammatory dermatology.",                (RED,)),
    "ZYME": CompanyInfo("Zymeworks",             "Bispecific antibodies and ADCs (zanidatamab for HER2+ cancers).",            (RED,)),
    "XBIO": CompanyInfo("Xenetic Biosciences",   "DNase-based oncology platform targeting NETs in tumors.",                    (RED,)),
    "ONVO": CompanyInfo("Organovo Holdings",     "3D-bioprinted tissue therapeutics, lead in IBD.",                            (RED,)),
    "RGC":  CompanyInfo("Regencell Bioscience",  "Traditional Chinese-medicine-based therapeutics for ADHD and autism.",       (RED,)),
    "LIPO": CompanyInfo("Lipocine",              "Oral testosterone (TLANDO) and other prodrug formulations.",                 (RED,)),
    "PRTG": CompanyInfo("Portage Biotech",       "Immuno-oncology pipeline (iNKT cell, adenosine pathway).",                   (RED,)),
    "CGEM": CompanyInfo("Cullinan Therapeutics", "Targeted oncology and autoimmune bispecifics (zipalertinib, CLN-978).",      (RED,)),
    "ANIX": CompanyInfo("Anixa Biosciences",     "Breast-cancer vaccine and CAR-T for ovarian cancer.",                        (RED,)),
    "BCDA": CompanyInfo("BioCardia",             "Autologous cardiac stem-cell therapy CardiAMP for heart failure.",           (RED,)),
    "BCRX": CompanyInfo("BioCryst Pharmaceuticals","Berotralstat (Orladeyo) oral prophylaxis for hereditary angioedema.",     (RED,)),
    "BFRI": CompanyInfo("Biofrontera",           "Ameluz photodynamic therapy for actinic keratosis.",                         (RED,)),
    "BIVI": CompanyInfo("BioVie",                "NE3107 for Alzheimer's and Parkinson's; bezisterim platform.",               (RED,)),
    "BPTH": CompanyInfo("Bio-Path Holdings",     "Antisense DNAbilize platform; prexigebersen for AML.",                       (RED,)),
    "CLRB": CompanyInfo("Cellectar Biosciences", "Iopofosine I-131 radiopharmaceutical for hematologic cancers.",              (RED,)),
    "CMRX": CompanyInfo("Chimerix",              "Dordaviprone (ONC201) for H3 K27M-mutant glioma.",                            (RED,)),
    "CNTB": CompanyInfo("Connect Biopharma",     "Rademikibart (IL-4Rα) for asthma and atopic dermatitis.",                    (RED,)),
    "CYTO": CompanyInfo("Altamira Therapeutics", "Intranasal RNA delivery (SemaPhore) and inner-ear therapeutics.",            (RED,)),
    "DRRX": CompanyInfo("DURECT",                "Larsucosterol for alcohol-associated hepatitis.",                            (RED,)),
    "DRUG": CompanyInfo("Bright Minds Biosciences","5-HT2C agonists for epilepsy and neuropsychiatric disorders.",            (RED,)),
    "ENSC": CompanyInfo("Ensysce Biosciences",   "Abuse- and overdose-resistant opioid prodrug platform.",                     (RED,)),
    "FBIO": CompanyInfo("Fortress Biotech",      "Diversified biopharma holding (CUTX-101, dermatology, oncology).",           (RED,)),
    "FBRX": CompanyInfo("Forte Biosciences",     "FB102 (CD122 antagonist) for autoimmune disease.",                           (RED,)),
    "GLSI": CompanyInfo("Greenwich LifeSciences","GP2 immunotherapy to prevent HER2/neu+ breast-cancer recurrence.",           (RED,)),
    "GOVX": CompanyInfo("GeoVax Labs",           "Vaccine platform for COVID, mpox, and oncology immunotherapy.",              (RED,)),
    "HOTH": CompanyInfo("Hoth Therapeutics",     "Atopic-dermatitis lotion HT-001 and oncology candidate HT-KIT.",             (RED,)),
    "IMNN": CompanyInfo("IMUNON",                "TheraPlas DNA-mediated IL-12 immunotherapy (GEN-1) for ovarian cancer.",     (RED,)),
    "INAB": CompanyInfo("IN8bio",                "Allogeneic gamma-delta T-cell therapies for AML and solid tumors.",          (RED,)),
    "KALA": CompanyInfo("KALA BIO",              "KPI-012 mesenchymal stem-cell secretome for persistent corneal defects.",   (RED,)),
    "LXRX": CompanyInfo("Lexicon Pharmaceuticals","Sotagliflozin (Inpefa) for heart failure; SGLT inhibitor pipeline.",        (RED,)),
    "MDXG": CompanyInfo("MiMedx Group",          "Placental-tissue allografts for chronic-wound and surgical recovery.",       (RED,)),
    "MRNS": CompanyInfo("Marinus Pharmaceuticals","Ganaxolone (ZTALMY) for CDKL5 deficiency and refractory seizures.",         (RED,)),
    "NVCT": CompanyInfo("Nuvectis Pharma",       "NXP800 (HSF1 pathway) for ARID1a-mutated ovarian cancer; NXP900 SRC/YES1.",  (RED,)),
    "ONCT": CompanyInfo("Oncternal Therapeutics","Zilovertamab (ROR1) ADC and CAR-T for hematologic and solid tumors.",        (RED,)),
    "PALI": CompanyInfo("Palatin Technologies",  "Melanocortin receptor agonists (Vyleesi; dry-eye PL9643).",                   (RED,)),
    "PRTA": CompanyInfo("Prothena",              "Antibodies for misfolded-protein neurodegeneration (prasinezumab, AL01211).",(RED,)),
    "RNAZ": CompanyInfo("TransCode Therapeutics","TTX-MC138 microRNA-10b inhibitor for metastatic cancer.",                    (RED,)),
    "SLDB": CompanyInfo("Solid Biosciences",     "SGT-003 gene therapy for Duchenne muscular dystrophy.",                      (RED,)),
    "SVRA": CompanyInfo("Savara",                "Molgramostim inhalation for autoimmune pulmonary alveolar proteinosis.",     (RED,)),
    "TLSA": CompanyInfo("Tiziana Life Sciences", "Intranasal foralumab (anti-CD3) for MS and Alzheimer's neuroinflammation.",  (RED,)),
    "VRPX": CompanyInfo("Virpax Pharmaceuticals","Non-opioid pain candidates including Probudur and Envelta.",                 (RED,)),
    "WINT": CompanyInfo("Windtree Therapeutics", "Istaroxime for cardiogenic shock; rostafuroxin for hypertension.",           (RED,)),
    "XCUR": CompanyInfo("Exicure",               "SNA-based therapeutics; restructuring around new pipeline assets.",          (RED,)),
    "ENVB": CompanyInfo("Enveric Biosciences",   "Psilocin-derived psychedelic therapeutics for psychiatric disorders.",       (RED,)),

    # ---------- Red + Gold (drug development meets AI / computational bio) ----------
    "ABSI": CompanyInfo("Absci",                 "Generative-AI protein design for de novo therapeutic antibodies.",           (RED, GOLD)),
    "BTAI": CompanyInfo("BioXcel Therapeutics",  "AI-driven drug repurposing; Igalmi for acute agitation.",                    (RED, GOLD)),
    "EVAX": CompanyInfo("Evaxion Biotech",       "AI-driven discovery of cancer and infectious-disease vaccines.",             (RED, GOLD)),
    "IPA":  CompanyInfo("ImmunoPrecise Antibodies","AI-augmented antibody discovery and engineering services.",                (RED, GOLD)),
    "BNGO": CompanyInfo("Bionano Genomics",      "Saphyr optical genome mapping for structural variant analysis.",             (RED, GOLD)),

    # ---------- Red + Green (animal + human pharma) ----------
    "JAGX": CompanyInfo("Jaguar Health",         "Crofelemer (Mytesi) GI drugs for humans and companion animals.",             (RED, GREEN)),

    # ---------- Green: agricultural / animal health ----------
    "ICCC": CompanyInfo("ImmuCell",              "Animal-health products for dairy cattle (First Defense, Mast Out).",         (GREEN,)),
    "BIOX": CompanyInfo("Bioceres Crop Solutions","HB4 drought-tolerant soybean and wheat traits; biological crop inputs.",    (GREEN,)),
    "AGRI": CompanyInfo("AgriForce Growing Systems","Vertical-farming systems and ag-tech IP for controlled-environment crops.",(GREEN,)),
    "AGFY": CompanyInfo("Agrify",                "Vertical-farm cultivation hardware and SaaS for cannabis growers.",          (GREEN,)),
    "PETV": CompanyInfo("PetVivo Holdings",      "Spryng injectable osteoarthritis device for dogs and horses.",               (GREEN,)),

    # ---------- Green + Blue (aquaculture biotech) ----------
    "AQB":  CompanyInfo("AquaBounty Technologies","Genetically engineered fast-growing AquAdvantage Atlantic salmon.",         (GREEN, BLUE)),

    # ---------- White: industrial biotech ----------
    "GEVO": CompanyInfo("Gevo",                  "Low-carbon ethanol and sustainable aviation fuel from agricultural feedstocks.",(WHITE,)),
    "CDXS": CompanyInfo("Codexis",               "Engineered enzymes for pharma manufacturing and life-science research.",     (WHITE,)),
    "DNMR": CompanyInfo("Danimer Scientific",    "PHA-based biodegradable bioplastics (Nodax) for packaging.",                 (WHITE,)),
    "AMRS": CompanyInfo("Amyris",                "Synthetic-biology fermentation platform for ingredients and consumer brands.",(WHITE,)),
    "ORGN": CompanyInfo("Origin Materials",      "Furanics platform converting biomass into bio-PET and other materials.",     (WHITE,)),

    # ---------- Grey: environmental ----------
    "LOOP": CompanyInfo("Loop Industries",       "Depolymerization technology that recycles low-value PET into virgin-grade resin.",(GREY,)),
    "NEPH": CompanyInfo("Nephros",               "Hollow-fiber ultrafilters for medical and commercial water purification.",   (GREY,)),

    # ---------- Yellow: food / nutrition ----------
    "CDXC": CompanyInfo("ChromaDex",             "Niagen (nicotinamide riboside) NAD+ precursor for healthy aging.",           (YELLOW,)),
    "BRFH": CompanyInfo("Barfresh Food Group",   "Frozen ready-to-blend smoothies and beverage products for foodservice.",     (YELLOW,)),
    "LWAY": CompanyInfo("Lifeway Foods",         "Probiotic kefir and cultured-dairy products.",                                (YELLOW,)),
}


def _screener_universe() -> dict[str, list[str]]:
    """Pull NASDAQ candidates, classify by industry, return folder -> tickers.

    Best-effort: if the NASDAQ API is unreachable we silently fall back to
    an empty screener set (curated INFO still applies).
    """
    try:
        from screener import biotech_candidates
        from classify import classify
    except Exception:
        return {f: [] for f in FOLDERS}

    out: dict[str, list[str]] = {f: [] for f in FOLDERS}
    try:
        candidates = biotech_candidates()
    except Exception:
        return out

    for row in candidates:
        sym = row["symbol"]
        if sym in INFO:  # curated entry already covers this ticker
            continue
        # Classify on industry + name only (no business summary at this stage)
        cats = classify(row["sector"], row["industry"], row["name"], "")
        for cat in cats:
            if cat in out:
                out[cat].append(sym)
    return out


def UNIVERSE() -> dict[str, list[str]]:
    """Curated INFO categories merged with screener-discovered tickers."""
    out: dict[str, list[str]] = {f: [] for f in FOLDERS}
    for ticker, info in INFO.items():
        for cat in info.categories:
            out[cat].append(ticker)
    for cat, syms in _screener_universe().items():
        out[cat].extend(syms)
    # De-dupe while preserving order (curated first)
    for cat in out:
        seen: set[str] = set()
        deduped = []
        for s in out[cat]:
            if s not in seen:
                seen.add(s)
                deduped.append(s)
        out[cat] = deduped
    return out


def all_tickers() -> list[str]:
    seen: set[str] = set(INFO.keys())
    out: list[str] = list(INFO.keys())
    for syms in _screener_universe().values():
        for s in syms:
            if s not in seen:
                seen.add(s)
                out.append(s)
    return out
