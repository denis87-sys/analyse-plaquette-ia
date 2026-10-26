import os
import re
import json
import base64
import hashlib
from pathlib import Path

import streamlit as st
import anthropic
from jinja2 import Environment
from weasyprint import HTML

# --- CONFIGURATION DE LA PAGE (Visuel d'origine) ---
st.set_page_config(page_title="Analyseur Immo IA", page_icon="🏢")
st.title("🏢 Analyseur de Plaquette Immobilière par IA")

# --- SYSTÈME D'AUTHENTIFICATION MULTI-UTILISATEURS ---
def verifier_authentification():
    """Gère l'écran de connexion multi-utilisateurs via st.secrets."""
    # Vérification de la présence du dictionnaire utilisateurs dans les secrets
    if "utilisateurs" not in st.secrets:
        st.error("❌ Configuration des utilisateurs absente dans les st.secrets.")
        return False

    # Si l'utilisateur est déjà connecté dans cette session
    if st.session_state.get("authentifie", False):
        return True

    # Écran de connexion
    st.markdown("<h2 style='text-align: center; color: #13294b;'>🔒 Espace Client Sécurisé — Due Diligence</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #666;'>Veuillez vous identifier avec vos accès personnels.</p>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        nom_utilisateur = st.text_input("Identifiant client :")
        mot_de_passe = st.text_input("Mot de passe :", type="password")

        if st.button("Se connecter 🔓", use_container_width=True):
            base_utilisateurs = st.secrets["utilisateurs"]
            
            # Vérification si l'identifiant existe et si le mot de passe correspond
            if nom_utilisateur in base_utilisateurs and mot_de_passe == base_utilisateurs[nom_utilisateur]:
                st.session_state["authentifie"] = True
                st.session_state["client_connecte"] = nom_utilisateur
                st.rerun()
            else:
                st.error("❌ Identifiant ou mot de passe incorrect.")

    return False

# Bloque l'exécution de l'application si l'utilisateur n'est pas connecté
if not verifier_authentification():
    st.stop()
else:
    # Petit message de bienvenue discret dans la barre latérale ou en en-tête
    st.sidebar.success(f"Connecté en tant que : **{st.session_state.get('client_connecte')}**")

# Dossier de cache local pour éviter de repayer l'API sur un même fichier PDF
CACHE_DIR = Path(".cache_analyses")
CACHE_DIR.mkdir(exist_ok=True)

# --- CLÉ API & SÉLECTEUR DE VERSION ---
if "ANTHROPIC_API_KEY" not in st.secrets:
    st.error("Clé ANTHROPIC_API_KEY introuvable dans les Secrets Streamlit.")
    st.stop()

api_key = st.secrets["ANTHROPIC_API_KEY"]
client = anthropic.Anthropic(api_key=api_key)

@st.cache_data(ttl=600)
def charger_modeles_actifs(_api_key):
    c = anthropic.Anthropic(api_key=_api_key)
    tous_les_modeles = [m.id for m in c.models.list().data]
    modeles_valides = [
        m for m in tous_les_modeles
        if "20241022" not in m and "20240620" not in m
    ]
    sonnets = [m for m in modeles_valides if "sonnet" in m.lower()]
    haikus = [m for m in modeles_valides if "haiku" in m.lower()]
    autres = [m for m in modeles_valides if m not in sonnets and m not in haikus]
    return sonnets + haikus + autres

try:
    modeles_disponibles = charger_modeles_actifs(api_key)
    options_selecteur = modeles_disponibles + ["🧪 Mode Test Gratuit (0 crédit API — Cache / Démo)"]
    modele_choisi = st.selectbox(
        "Version du modèle Claude :",
        options=options_selecteur,
        index=0
    )
except Exception as e:
    st.error(f"Impossible de récupérer la liste des modèles : {e}")
    st.stop()

# Case à cocher du cache intelligent (activée par défaut)
utiliser_cache = st.checkbox(
    "💾 Activer le cache intelligent (évite de repayer si vous cliquez deux fois sur le même PDF)",
    value=True
)


# --- STRUCTURE PAR DÉFAUT COMPLÈTE ---
def obtenir_structure_defaut():
    return {
        "1_synthese_et_verdict": {
            "verdict_conditionnel": "Non mentionné",
            "scenarios": [],
            "quatre_alertes": [],
            "prochaine_etape": "Non mentionné"
        },
        "2_identification_bien": {
            "caracteristiques": [],
            "donnees_manquantes": []
        },
        "3_localisation_et_cadre": {
            "accessibilite_et_bruit": "Non mentionné",
            "zone_affectation_projets": "Non mentionné",
            "fiscalite_communale": "Non mentionné",
            "compatibilite_criteres_utilisateur": "Non mentionné"
        },
        "4_lecture_critique": [],
        "5_copropriete_et_batiment": {
            "points_favorables": [],
            "points_a_instruire": [],
            "energie_et_calendrier_legal": "Non mentionné"
        },
        "6_valorisation": {
            "prix_m2_annonce": "Non mentionné",
            "prix_m2_recalcule": "Non mentionné",
            "comparables_estimes": [],
            "grille_ajustement": [],
            "test_rendement_locatif": "Non mentionné"
        },
        "7_matrice_risques": [],
        "8_strategie_offre": {
            "sequence_demarches": [],
            "arguments_negociation_par_poids": [],
            "atouts_vendeur": []
        },
        "9_couts_acquisition_detention": {
            "frais_acquisition_cibles": "Non mentionné",
            "cout_total_entree": "Non mentionné",
            "cout_detention_annuel_reel": "Non mentionné"
        },
        "10_financement": {
            "tableau_financement": [],
            "hypotheses_prix_demande": "Non mentionné",
            "hypotheses_prix_cible": "Non mentionné",
            "composition_fonds_propres": "Non mentionné",
            "modalites_amortissement_2e_rang": "Non mentionné"
        },
        "11_fiscalite": {
            "taux_communal_et_comparaison": "Non mentionné",
            "impact_impot_foncier": "Non mentionné",
            "forfait_entretien_et_economie_3a": "Non mentionné",
            "impact_suppression_valeur_locative_2029": "Non mentionné"
        },
        "annexe_a_documents_a_reclamer": [],
        "annexe_b_points_visite": [],
        "conclusion": {
            "constats_decisifs": [],
            "sources_consultees": []
        }
    }


# --- DONNÉES DE DÉMO POUR LE MODE TEST GRATUIT (0 CRÉDIT API) ---
DONNEES_DEMO_TEST = {
    "1_synthese_et_verdict": {
        "verdict_conditionnel": "Bien attractif et rare (RDC de plain-pied avec jardin à usage exclusif de 148 m² [A], deux box fermés avec borne [V], proche lac et EPFL), mais dossier incomplet : aucun plan coté, CECB, règlement PPE, PV d'AG ni détail des charges. Prix tout compris de CHF 1'600'000 [A] (CHF 14'815/m² sur 108 m² annoncés), en haut de fourchette [E]. Pas d'offre ferme avant réception des pièces. Offre conditionnelle envisageable autour de CHF 1'360'000 hors parkings + CHF 80'000 pour les deux box.",
        "scenarios": [
            {
                "type": "A favorable",
                "valeur_estimee_fourchette": "CHF 1'400'000 - 1'520'000 hors parkings [E] (+ parkings CHF 70'000 - 90'000 [E])",
                "offre_ouverture": "CHF 1'360'000 + CHF 80'000 parkings (CHF 1'440'000)",
                "prix_plafond": "CHF 1'480'000 + CHF 80'000 parkings (CHF 1'560'000)"
            },
            {
                "type": "B dégradé",
                "valeur_estimee_fourchette": "CHF 1'280'000 - 1'400'000 hors parkings [E] (local inférieur sans valeur habitable, nuisances routières RC1)",
                "offre_ouverture": "CHF 1'250'000 + CHF 70'000 parkings",
                "prix_plafond": "CHF 1'340'000 + CHF 80'000 parkings"
            },
            {
                "type": "C risque spécifique",
                "valeur_estimee_fourchette": "CHF 1'150'000 - 1'300'000 hors parkings [E] (véranda ou salle d'eau du sous-sol non autorisées)",
                "offre_ouverture": "CHF 1'150'000 avec retenue de régularisation",
                "prix_plafond": "CHF 1'240'000 si régularisation à charge vendeur"
            }
        ],
        "quatre_alertes": [
            "Dossier sans plans cotés, CECB, règlement PPE ni PV : les surfaces (108, 9,5, 32 et 10,4 m²) [A] et la part de circulation (entrée + hall) sont invérifiables.",
            "Local inférieur de 32 m² déclaré non habitable [A] mais équipé de douche, WC et buanderie [V] : risque de non-conformité sanitaire et d'affectation.",
            "Véranda de 9,5 m² [A] et jardin de 148 m² [A] : droit d'usage exclusif sur partie commune PPE [E], permis de construire et accord PPE à vérifier.",
            "Prix effectif de CHF 1'600'000 [A] avec box à CHF 100'000 en sus et charges de CHF 720/mois non détaillées ; proximité immédiate de la route cantonale RC1 [V]."
        ],
        "prochaine_etape": "Réclamer par écrit à l'agence les pièces de l'Annexe A (plans cotés SIA 416, CECB, règlement PPE, 3 derniers PV, estimation fiscale du lot) avant toute offre."
    },
    "2_identification_bien": {
        "caracteristiques": [
            {"cle": "Localisation", "valeur_et_fiabilite": "Saint-Sulpice (VD), secteur embouchure de la Venoge / Route du Lac [A]"},
            {"cle": "Surface habitable chauffée & circulation", "valeur_et_fiabilite": "108 m² annoncés [A] ; part de circulation (entrée + hall) impossible à calculer sans plans cotés"},
            {"cle": "Annexes (véranda, local inférieur, cave)", "valeur_et_fiabilite": "Véranda 9,5 m² [A], local inférieur aménagé 32 m² non habitable [A], cave 10,4 m² [A]"},
            {"cle": "Jardin extérieur", "valeur_et_fiabilite": "148 m² en droit d'usage exclusif sur partie commune PPE [E]"},
            {"cle": "Prix demandé", "valeur_et_fiabilite": "CHF 1'500'000 + CHF 100'000 (2 box fermés avec borne, lot n°26 [V]) = CHF 1'600'000 [A]"},
            {"cle": "Charges PPE", "valeur_et_fiabilite": "CHF 720 / mois (CHF 8'640 / an) [A]"}
        ],
        "donnees_manquantes": [
            "Plans cotés SIA 416 et coupes", "Certificat CECB et SRE du bâtiment", "Règlement de PPE et millièmes",
            "PV des 3 dernières AG et fonds de rénovation", "Estimation fiscale du lot (assiette impôt foncier)", "Permis d'habiter"
        ]
    },
    "3_localisation_et_cadre": {
        "accessibilite_et_bruit": "Rive du lac, proximité EPFL/UNIL [V]. Bâtiment bordant la RC1 avec ligne de bus [V] : exposition au bruit routier à vérifier.",
        "zone_affectation_projets": "Zone résidentielle [E]. Parcelle avec courts de tennis au nord-ouest [V] pouvant faire l'objet d'un développement futur.",
        "fiscalite_communale": "Saint-Sulpice : taux communal de 55 points (arrêté 2026) [V], très avantageux comparé à la moyenne cantonale vaudoise de 69,4 points (-14,4 points).",
        "compatibilite_criteres_utilisateur": "Adapté à un couple recherchant un plain-pied fiscalement attractif ; limité à 2 chambres."
    },
    "4_lecture_critique": [
        {"formulation_vendeur": "Magnifique souplex avec jardin de 148 m²", "realite_terrain": "Seul le RDC (108 m²) est habitable [A]. Le sous-sol (32 m²) est non habitable et le jardin est une partie commune à usage exclusif [E]."},
        {"formulation_vendeur": "Local non habitable de 32 m² entièrement aménagé", "realite_terrain": "Équipé de douche, WC et buanderie [V]. Ne peut compter comme surface habitable et se valorise à 30-40 % du prix/m² habitable [E]."},
        {"formulation_vendeur": "Deux places en box fermé CHF 100'000 en sus", "realite_terrain": "CHF 50'000/place [A] contre CHF 35'000-45'000 sur le marché local [E]. Droits de mutation vaudois (~4,5 %) applicables dessus."}
    ],
    "5_copropriete_et_batiment": {
        "points_favorables": ["Construction récente (env. 2012-2020) avec toiture végétalisée [V]", "Deux box fermés avec borne de recharge [V]", "Accès plain-pied RDC [V]"],
        "points_a_instruire": ["Dotation du fonds de rénovation", "Conformité de la salle d'eau au sous-sol", "Étanchéité du niveau semi-enterré"],
        "energie_et_calendrier_legal": "Immeuble récent a priori non concerné par le décret DACCE (chauffages électriques, échéance 01.01.2033) [E]. Selon la LVLEne vaudoise de février 2026, CECB obligatoire au-delà de 750 m² SRE (assainissement 2037 classe G, 2042 classe F) [V]. Réclamer le CECB."
    },
    "6_valorisation": {
        "prix_m2_annonce": "CHF 13'889 / m² hors parkings (CHF 1'500'000 / 108 m²) [A] ; CHF 14'815 / m² parkings inclus.",
        "prix_m2_recalcule": "Surface pondérée estimée à ~140 m² (108 m² hab. + 50 % véranda 4,75 m² + 40 % sous-sol 12,8 m² + 10 % jardin 14,8 m²) [E], soit CHF 10'714 / m² pondéré hors parkings.",
        "comparables_estimes": [
            {"description": "PPE récente avec jardin, Saint-Sulpice, 3,5-4,5 p. (110 m²)", "prix_m2": "CHF 11'500 - 13'000 / m² [E]"},
            {"description": "PPE récente proche lac, Préverenges / Morges (115 m²)", "prix_m2": "CHF 10'500 - 12'500 / m² [E]"},
            {"description": "PPE récente, Ecublens / EPFL (105 m²)", "prix_m2": "CHF 9'500 - 11'500 / m² [E]"}
        ],
        "grille_ajustement": [
            {"poste": "Surface habitable de base (108 m²)", "scenario_a": "CHF 1'296'000 [E]", "scenario_b": "CHF 1'210'000 [E]", "justification": "Base CHF 12'000/m² (A) vs CHF 11'200/m² (B)"},
            {"poste": "Véranda (9,5 m²) + Jardin (148 m²)", "scenario_a": "+ CHF 115'000 [E]", "scenario_b": "+ CHF 85'000 [E]", "justification": "Pondération 50 % véranda et 10 % jardin"},
            {"poste": "Local inférieur (32 m²) + Cave (10,4 m²)", "scenario_a": "+ CHF 85'000 [E]", "scenario_b": "+ CHF 45'000 [E]", "justification": "Valorisé comme surface annexe non habitable"},
            {"poste": "Décote bruit RC1 / incertitude documentaire", "scenario_a": "- CHF 36'000 [E]", "scenario_b": "- CHF 60'000 [E]", "justification": "Proximité route cantonale et absence de plans"}
        ],
        "test_rendement_locatif": "Loyer de marché estimé à CHF 4'300/mois (CHF 51'600/an) [E]. Rendement brut de 3,2 % sur CHF 1'600'000 (net ~1,8 %), confirmant un bien d'usage propre."
    },
    "7_matrice_risques": [
        {"numero": 1, "risque": "Surfaces non vérifiées (plans absents)", "gravite": "Elevée", "probabilite": "Moyenne", "impact_chiffre": "CHF 60'000 - 120'000 [E]", "qui_peut_lever_le_doute": "Plans cotés SIA 416 / géomètre"},
        {"numero": 2, "risque": "Local de 32 m² aménagé sans autorisation sanitaire", "gravite": "Elevée", "probabilite": "Moyenne", "impact_chiffre": "CHF 60'000 - 110'000 [E]", "qui_peut_lever_le_doute": "Commune / Permis d'habiter"},
        {"numero": 3, "risque": "Véranda ou aménagements sans accord PPE", "gravite": "Moyenne", "probabilite": "Moyenne", "impact_chiffre": "CHF 15'000 - 40'000 [E]", "qui_peut_lever_le_doute": "Règlement PPE et PV d'AG"},
        {"numero": 4, "risque": "Charges PPE élevées / fonds de rénovation", "gravite": "Moyenne", "probabilite": "Moyenne", "impact_chiffre": "CHF 20'000 - 50'000 [E]", "qui_peut_lever_le_doute": "Comptes PPE et 3 derniers PV"}
    ],
    "8_strategie_offre": {
        "sequence_demarches": [
            "Réclamer les pièces de l'Annexe A", "Visite technique avec télémètre laser (Annexe B)",
            "Validation bancaire sur CHF 1'560'000", "Offre conditionnelle écrite dissociant appartement et parkings"
        ],
        "arguments_negociation_par_poids": [
            "1. Local de 32 m² non habitable à valoriser comme surface annexe",
            "2. Box facturés CHF 100'000 contre CHF 70'000-85'000 sur le marché",
            "3. Exposition au bruit de la RC1 et dossier technique incomplet"
        ],
        "atouts_vendeur": ["RDC avec jardin de 148 m² rare à Saint-Sulpice", "Fiscalité communale très attractive (55 pts)", "Immeuble récent"]
    },
    "9_couts_acquisition_detention": {
        "frais_acquisition_cibles": "Vaud ~4,5 % (mutation 3,3 %, notaire et RF ~1,2 %) + cédule ~CHF 3'000 [E], soit ~CHF 75'000 au prix demandé (CHF 73'200 au prix cible).",
        "cout_total_entree": "CHF 1'675'000 au prix demandé ; CHF 1'633'200 au prix cible de CHF 1'560'000.",
        "cout_detention_annuel_reel": "Intérêts effectifs (1,75 % sur CHF 1'248'000) = CHF 21'840 + charges PPE CHF 8'640 [A] + impôt foncier et entretien ~CHF 6'500 [E] = ~CHF 37'000/an hors amortissement (CHF 52'600/an avec amortissement)."
    },
    "10_financement": {
        "tableau_financement": [
            {"poste": "Prix d'acquisition (parkings inclus)", "prix_demande": "CHF 1'600'000 [A]", "prix_cible": "CHF 1'560'000 [E]"},
            {"poste": "Fonds propres 20 % + Frais (~4,5 % + cédule)", "prix_demande": "CHF 320'000 + CHF 75'000 = CHF 395'000", "prix_cible": "CHF 312'000 + CHF 73'200 = CHF 385'200"},
            {"poste": "Prêt 80 % (1er rang 65 % / 2e rang 15 %)", "prix_demande": "CHF 1'280'000 (1'040'000 / 240'000)", "prix_cible": "CHF 1'248'000 (1'014'000 / 234'000)"},
            {"poste": "Amortissement annuel 2e rang (sur 15 ans)", "prix_demande": "CHF 16'000 / an", "prix_cible": "CHF 15'600 / an"},
            {"poste": "Charge théorique bancaire (5 % + 1 % + amort.)", "prix_demande": "CHF 96'000 / an", "prix_cible": "CHF 93'600 / an"},
            {"poste": "Revenu brut annuel requis (tenue à 33 %)", "prix_demande": "CHF 290'900 / an [E]", "prix_cible": "CHF 283'600 / an [E]"}
        ],
        "hypotheses_prix_demande": "Fonds propres CHF 395'000 (frais inclus), prêt CHF 1'280'000, charge théorique CHF 96'000/an, revenu requis CHF 290'900/an [E].",
        "hypotheses_prix_cible": "Fonds propres CHF 385'200 (frais inclus), prêt CHF 1'248'000, charge théorique CHF 93'600/an, revenu requis CHF 283'600/an [E].",
        "composition_fonds_propres": "Minimum 10 % de fonds propres durs (CHF 156'000 à 160'000 : épargne, titres ou 3e pilier A) + frais d'acquisition en liquidités. Solde de 10 % via 2e pilier (mise en gage préférable au retrait).",
        "modalites_amortissement_2e_rang": "Amortissement requis de CHF 15'600 à 16'000/an, supérieur au plafond 3a 2026 d'un salarié affilié (CHF 7'258/an) et d'un couple affilié (CHF 14'516/an sur 2 comptes) [V]. Combinaison obligatoire : CHF 14'516/an en indirect (couple) + CHF 1'084 à 1'484/an en direct (ou CHF 7'258 indirect + ~CHF 8'500 direct pour une personne seule)."
    },
    "11_fiscalite": {
        "taux_communal_et_comparaison": "Saint-Sulpice : 55 points (arrêté 2026) [V], très avantageux face à la moyenne cantonale vaudoise (69,4 pts), Morges (67) ou Lausanne (78,5).",
        "impact_impot_foncier": "Impôt foncier de 1,0 à 1,5 ‰ de l'estimation fiscale du lot (à réclamer en Annexe A, estimé à CHF 1'200 - 1'800/an [E]).",
        "forfait_entretien_et_economie_3a": "Bâtiment < 20 ans : forfait d'entretien VD de 20 % de la valeur locative jusqu'en 2028 [V]. Économie fiscale 3a d'env. CHF 2'100 à 4'400/an.",
        "impact_suppression_valeur_locative_2029": "Suppression de la valeur locative au 01.01.2029 : travaux d'entretien à réaliser avant fin 2028 pour rester déductibles. Primo-acquéreurs : intérêts déductibles 10 ans (plafond CHF 5'000 seul / CHF 10'000 couple, dégressif de 10 %/an) [V]."
    },
    "annexe_a_documents_a_reclamer": [
        {"document": "Plans cotés SIA 416 de tous les niveaux et coupe", "permet_de_trancher": "Surface habitable exacte, part de circulation et hauteur du sous-sol", "numero_risque_lie": 1},
        {"document": "Estimation fiscale officielle du lot et extrait RF", "permet_de_trancher": "Assiette exacte de l'impôt foncier communal et servitudes", "numero_risque_lie": 4},
        {"document": "Permis de construire, permis d'habiter et autorisation véranda", "permet_de_trancher": "Légalité de la salle d'eau au sous-sol et de la véranda", "numero_risque_lie": 2},
        {"document": "Règlement PPE, comptes, fonds de rénovation et 3 derniers PV", "permet_de_trancher": "Usage exclusif du jardin, détail des CHF 720/mois et travaux futurs", "numero_risque_lie": 3},
        {"document": "Certificat CECB du bâtiment", "permet_de_trancher": "Classe énergétique et obligations LVLEne fév. 2026 (> 750 m² SRE)", "numero_risque_lie": 4}
    ],
    "annexe_b_points_visite": [
        {"point_a_verifier_sur_place": "Mesurer au télémètre laser chaque pièce, l'entrée/hall (part de circulation) et la hauteur sous plafond du local de 32 m²"},
        {"point_a_verifier_sur_place": "Vérifier l'absence d'humidité ou de condensation dans le local inférieur semi-enterré"},
        {"point_a_verifier_sur_place": "Contrôler si la véranda de 9,5 m² est chauffée ou non et vérifier ses vitrages"},
        {"point_a_verifier_sur_place": "Mesurer le bruit routier (RC1 et bus) en heure de pointe depuis le jardin et les chambres"},
        {"point_a_verifier_sur_place": "Tester l'accès au box double n°26 et relever le raccordement de la borne électrique"}
    ],
    "conclusion": {
        "constats_decisifs": [
            "Localisation recherchée à Saint-Sulpice avec une fiscalité communale très avantageuse (55 points contre 69,4 de moyenne cantonale vaudoise).",
            "Prix demandé de CHF 1'600'000 parkings inclus élevé au regard des 32 m² en sous-sol non habitables et de l'absence de plans cotés.",
            "Dossier documentaire incomplet interdisant toute offre ferme avant vérification des pièces de l'Annexe A (dont l'estimation fiscale et le CECB).",
            "Amortissement du 2e rang (CHF 15'600/an au prix cible) excédant le plafond 3a 2026 même pour un couple (CHF 14'516/an), imposant un mix indirect + direct.",
            "Cible de négociation cohérente autour de CHF 1'440'000 à CHF 1'520'000 parkings inclus, sous réserve de régularité administrative."
        ],
        "sources_consultees": [
            "Arrêtés d'imposition communaux vaudois 2026 (DGAIC / FAO VD : faovd.ch)",
            "Loi vaudoise sur l'énergie (LVLEne, février 2026) et Décret DACCE (échéance 2033)",
            "Plafonds fédéraux OPP3 (3e pilier A) 2026 (CHF 7'258 / CHF 14'516 / CHF 36'288)"
        ]
    }
}


def reparer_et_fermer_json(texte):
    texte = re.sub(r"```(?:json)?", "", texte).strip()

    debut = texte.find('{"1_synthese_et_verdict"')
    if debut == -1:
        debut = texte.find("{")
    if debut == -1:
        raise ValueError(f"Aucun JSON détecté dans la réponse de l'IA. Début reçu : {texte[:200]}")

    json_str = texte[debut:]

    fin = json_str.rfind("}")
    if fin != -1:
        try:
            return json.loads(json_str[:fin + 1])
        except json.JSONDecodeError:
            pass

    out = []
    stack = []
    in_string = False
    escape = False
    n = len(json_str)

    for i, ch in enumerate(json_str):
        if escape:
            out.append(ch)
            escape = False
            continue
        if ch == "\\":
            out.append(ch)
            escape = True
            continue
        if ch == '"':
            if not in_string:
                in_string = True
                out.append(ch)
            else:
                j = i + 1
                while j < n and json_str[j] in " \t\r\n":
                    j += 1
                next_ch = json_str[j] if j < n else ""
                if next_ch in [":", ",", "}", "]", ""]:
                    in_string = False
                    out.append(ch)
                else:
                    out.append('\\"')
            continue

        if in_string:
            if ch == "\n":
                out.append("\\n")
            elif ch == "\r":
                continue
            elif ch == "\t":
                out.append("\\t")
            else:
                out.append(ch)
        else:
            if ch in "{[":
                stack.append("}" if ch == "{" else "]")
                out.append(ch)
            elif ch in "}]":
                if stack and stack[-1] == ch:
                    stack.pop()
                    out.append(ch)
                    if not stack:
                        break
            else:
                out.append(ch)

    repare = "".join(out)
    if in_string:
        repare += '"'

    repare = re.sub(r"[,:\s]+$", "", repare)

    while stack:
        repare = re.sub(r",\s*$", "", repare)
        repare += stack.pop()

    repare = re.sub(r",\s*([}\]])", r"\1", repare)
    return json.loads(repare)


def normaliser_et_fusionner(donnees_extraites):
    """Fusionne avec la structure par défaut et corrige les éventuels alias de clés utilisés par Claude."""
    resultat = obtenir_structure_defaut()
    if not isinstance(donnees_extraites, dict):
        return resultat

    for cle, valeur in donnees_extraites.items():
        if cle in resultat and isinstance(resultat[cle], dict) and isinstance(valeur, dict):
            for k, v in valeur.items():
                if v is not None and v != "":
                    resultat[cle][k] = v
        elif valeur is not None:
            resultat[cle] = valeur

    # Normalisation Section 3 (au cas où Claude utilise un synonyme de clé)
    s3 = resultat["3_localisation_et_cadre"]
    if s3.get("accessibilite_et_bruit") in [None, "", "Non mentionné"]:
        for alias in ["accessibilite", "accessibilite_bruit", "bruit", "transports_et_bruit"]:
            if s3.get(alias):
                s3["accessibilite_et_bruit"] = s3[alias]
                break

    # Normalisation Section 11 (si Claude remplit un sous-ensemble des champs fiscaux)
    s11 = resultat["11_fiscalite"]
    if s11.get("taux_communal_et_comparaison") in [None, "", "Non mentionné"]:
        for alias in ["taux_communal", "fiscalite_communale"]:
            if s11.get(alias):
                s11["taux_communal_et_comparaison"] = s11[alias]
                break
    if s11.get("impact_impot_foncier") in [None, "", "Non mentionné"]:
        for alias in ["impot_foncier", "impot_foncier_et_forfait_entretien"]:
            if s11.get(alias):
                s11["impact_impot_foncier"] = s11[alias]
                break

    return resultat


def est_analyse_complete(donnees: dict) -> bool:
    """Vérifie que le JSON n'a pas été tronqué en cours de route avant d'accepter ou mettre en cache."""
    if not isinstance(donnees, dict):
        return False
    try:
        # Vérification que les sections 4, 6, 7, 9, 10, 11 et les annexes sont bien remplies
        if not donnees.get("4_lecture_critique"):
            return False
        if not donnees.get("7_matrice_risques"):
            return False
        if donnees.get("6_valorisation", {}).get("prix_m2_annonce", "Non mentionné") == "Non mentionné":
            return False
        if donnees.get("9_couts_acquisition_detention", {}).get("cout_total_entree", "Non mentionné") == "Non mentionné":
            return False
        if not donnees.get("annexe_a_documents_a_reclamer"):
            return False
        if not donnees.get("annexe_b_points_visite"):
            return False
        return True
    except Exception:
        return False


def extraire_donnees_claude(response):
    text_blocks = [getattr(b, "text", "") for b in response.content if getattr(b, "text", "")]
    raw_text = "\n".join(text_blocks).strip()

    if "{" not in raw_text:
        thinking_blocks = [getattr(b, "thinking", "") for b in response.content if getattr(b, "thinking", "")]
        raw_text = "\n".join(thinking_blocks).strip()

    donnees_extraites = reparer_et_fermer_json(raw_text)
    return normaliser_et_fusionner(donnees_extraites)


# --- FILTRES JINJA2 POUR LES BADGES [A] [E] [V] ET LE NETTOYAGE DES CHEVRONS ---
def format_badges(text):
    if not isinstance(text, str):
        return str(text)
    # Convertit aussi bien [A], [E], [V] que [V photo], [V photos], [A, carte], etc.
    text = re.sub(r"\[\s*A(?:\s*[,/]\s*[^\]]+)?\s*\]", r'<span class="badge-rel badge-A">A</span>', text)
    text = re.sub(r"\[\s*E(?:\s*[,/]\s*[^\]]+)?\s*\]", r'<span class="badge-rel badge-E">E</span>', text)
    text = re.sub(r"\[\s*V(?:\s+[^\]]+|\s*[,/]\s*[^\]]+)?\s*\]", r'<span class="badge-rel badge-V">V</span>', text)
    return text

def clean_quotes(text):
    if not isinstance(text, str):
        return str(text)
    return text.strip(" «»\"'<>")

def rendre_html_avec_filtres(template_str, data):
    env = Environment()
    env.filters["format_badges"] = format_badges
    env.filters["clean_quotes"] = clean_quotes
    return env.from_string(template_str).render(data=data)


# --- PROMPT SYSTÈME COMPLET (Intégration intégrale de Prompt.txt) ---
SYSTEM_PROMPT = """
# RÔLE ET EXPERTISE
Tu es analyste immobilier senior, spécialisé dans la due diligence pré-acquisition en Suisse romande. L'utilisateur te fournit la documentation de vente d'un bien (plaquette, annonce, plans, CECB, extraits divers). Ta mission est de produire une note d'analyse d'acquisition exhaustive et critique en français.

# 1. MÉTHODOLOGIE (À APPLIQUER STRICTEMENT)
1. Analyse documentaire : Lis TOUTE la documentation, y compris les plans, le CECB et les annexes graphiques. Examine visuellement les pages de plans avec la plus grande attention (les cotes sont souvent petites). Les plans priment systématiquement sur le texte commercial.
2. Confrontation systématique :
   - Additionne les surfaces cotées des pièces et compare à la surface annoncée ;
   - Distingue surface habitable chauffée, surface PPE brute (murs compris), surface pondérée, balcons, vérandas non chauffées et locaux non habitables ;
   - Vérifie la cohérence du nombre de chambres avec le nombre de pièces annoncé ;
   - Relève tout écart entre le texte et les plans (jardin, balcon, dépendances) ;
   - Repère ce qui est décrit comme existant mais figure autrement sur les plans (locaux livrés bruts, aménagements postérieurs, annexes non autorisées) ;
   - Calcule la part de circulation (entrée + hall) dans la surface chauffée.
3. Données de marché et cadre légal énergétique :
   - Évalue le prix au m² moyen et médian de la commune (et évolution 1 an / 5 ans), 3 à 5 comparables pertinents (avec surface, prix annexes comprises et prix au m²), et le loyer de marché au m² pour le test de rendement ;
   - Applique le cadre légal énergétique applicable au canton et à l'objet :
     * Décret vaudois DACCE : chauffages et chauffe-eau électriques, assainissement au 1er janvier 2033, dispense en classe C, prolongation de 5 ans en classes D ou E ;
     * Loi vaudoise sur l'énergie LVLEne de février 2026 : fossile remplacé en fin de vie, 2042 avant 2020 et 2047 après ; CECB obligatoire au-delà de 750 m² SRE, assainissement jusqu'à classe D d'ici 2037 pour les G et 2042 pour les F ;
     * Loi valaisanne sur l'énergie depuis le 1er janvier 2025 : réduction de la part non renouvelable au remplacement, sauf classe CECB D ou meilleure ; pas de délai couperet pour l'électrique.
4. Fiabilité des données :
   Marque chaque donnée avec les balises exactes : [A] = annoncé par le vendeur, non vérifié · [E] = estimation ou hypothèse de l'analyste · [V] = établi par une pièce au dossier. N'invente jamais une donnée absente : écris qu'elle manque et range-la dans les documents à réclamer.

# 2. HYPOTHÈSES DE CALCUL STANDARD
- Charge théorique : taux calculatoire 5 %, entretien 1 %, amortissement du 2e rang sur 15 ans jusqu'à 65 % de la valeur, tenue à 33 % du revenu brut.
- Frais d'acquisition : Vaud ~4,5 % (mutation 3,3 %, notaire et RF ~1,2 %, cédule ~3'000 CHF) ; Valais ~2,5 % (mutation 1,5 %, RF 0,2 %, notaire 0,5-0,7 %). Les droits de mutation s'appliquent aussi aux places de parc vendues séparément.
- Coût de détention réel : taux effectif 1,5 à 2,0 %, à distinguer du taux calculatoire.
- Ordres de grandeur travaux : PAC air-eau en remplacement d'un chauffage électrique décentralisé 55 à 85k CHF bruts (production 40-50k, distribution hydraulique à créer 15-35k, soit ~80 CHF/m² en radiateurs et ~180 CHF/m² en sol) ; cuisine et salles d'eau 60 à 150k CHF ; fenêtres 30 à 60k CHF.

# 3. FISCALITÉ COMMUNALE — À CHIFFRER POUR CHAQUE BIEN
- Le taux communal s'exprime en points (% de l'impôt cantonal de base). Coefficient cantonal vaudois : 155 points. Moyenne cantonale communale : 69,4 points. Entre Lonay (55) et Lausanne (78,5), l'écart d'impôt communal dépasse 40 % à revenu égal.
- Sources officielles FAO VD 2026 (DGAIC) : https://faovd.ch/autres/1423/68af07c3ef7e7504704310.pdf et https://faovd.ch/autres/1449/692712fd89dc6427927368.pdf
- N'écris jamais qu'un taux est « élevé » ou « avantageux » sans l'avoir comparé à 69,4 points.
- Repères vérifiés (arrêtés 2026) : Lonay 55 pts (8e, très avantageux), Saint-Sulpice 55 pts (très avantageux, arrêté 2026), Denges 62 pts (44e), Ecublens 62,5 pts (49e), Préverenges 65 pts (70e), Montreux 65 pts (sous la moyenne, arrêté 2026), Morges 67 pts (103e, arrêté 2026), Hautemorges (Pampigny) 68 pts (proche moyenne), Savigny 69 pts (119e, dans la moyenne), MOYENNE CANTONALE 69,4 pts, Prilly 72,5 pts (187e), Lausanne 78,5 pts (278e, parmi les plus chers).
- Impôt foncier : 1,0 à 1,5 ‰ de l'estimation fiscale selon la commune (Montreux 1,5 ‰, Aigle 1,20 ‰). À chiffrer dans le coût de détention dès que l'estimation fiscale est connue, et à réclamer systématiquement en Annexe A sinon.
- Forfait d'entretien déductible (VD, barème 2026) : occupé par le propriétaire, 30 % de la valeur locative si le bâtiment a > 20 ans, 20 % s'il en a moins ; loué, 20 % du revenu locatif net au-delà de 20 ans, 10 % en deçà. Un bâtiment ancien ouvre donc un forfait plus large — jusqu'à fin 2028 seulement (travaux à réaliser avant fin 2028 pour rester déductibles avant la suppression de la valeur locative au 1er janvier 2029 ; primo-acquéreurs : intérêts déductibles 10 ans, plafond 5'000 CHF célibataire / 10'000 CHF couple, dégressif de 10 % par an).

# 4. TROISIÈME PILIER — PLAFONDS 2026 ET USAGE
Plafonds de déduction 3a, exercice 2026 :
- personne affiliée à une caisse de pension : CHF 7'258 par an ;
- personne non affiliée (indépendant) : 20 % du revenu net, max CHF 36'288 par an ;
- couple dont les deux conjoints sont affiliés et exercent une activité lucrative : CHF 14'516 au total (deux fois 7'258 sur deux comptes distincts) ;
- depuis 2026, le rachat rétroactif des lacunes de cotisation 3a est possible, sous conditions.
Traite obligatoirement en section 10 :
1. Amortissement indirect du 2e rang : compare systématiquement l'amortissement annuel requis aux plafonds ci-dessus (<= 7'258 CHF : intégral sur un seul 3a ; entre 7'258 et 14'516 CHF : intégral possible seulement avec deux 3a en couple, sinon mix direct/indirect ; > 14'516 CHF : combinaison inévitable, indique la part amortissable indirectement et le solde à amortir directement). Rappelle l'arbitrage avec la réforme 2029.
2. Constitution des fonds propres : le 3a compte parmi les fonds propres « durs » (couvre les 10 % minimum exigibles hors 2e pilier). Si résidence secondaire : pas de 2e pilier, 30-40 % de fonds propres, charges cumulées avec la résidence principale.

# 5. RÈGLE CRITIQUE POUR LE FORMAT JSON (OBLIGATOIRE : REMPLIR LES 11 SECTIONS ET ANNEXES)
- Commence IMMÉDIATEMENT ta réponse par le caractère { et termine par }. Aucun texte ni balise markdown avant ou après.
- N'utilise JAMAIS de guillemets doubles droits (") à l'intérieur de tes textes : utilise exclusivement des apostrophes (') ou guillemets français (« et »).
- Sois dense, synthétique et direct (2 à 3 phrases par champ texte, 5 à 7 lignes par tableau) afin que TOUTES les sections de 1 à 11, les tableaux (comparables, grille_ajustement, tableau_financement, matrice_risques), les annexes A et B et la conclusion soient 100 % remplis sans jamais être tronqués.

Structure JSON stricte à remplir intégralement :
{
  "1_synthese_et_verdict": {
    "verdict_conditionnel": "string (1 paragraphe dense)",
    "scenarios": [
      {
        "type": "A favorable | B dégradé | C risque spécifique",
        "valeur_estimee_fourchette": "string",
        "offre_ouverture": "string",
        "prix_plafond": "string"
      }
    ],
    "quatre_alertes": ["string (exactement 4 alertes)"],
    "prochaine_etape": "string"
  },
  "2_identification_bien": {
    "caracteristiques": [{"cle": "string (inclure part de circulation entrée+hall)", "valeur_et_fiabilite": "string"}],
    "donnees_manquantes": ["string"]
  },
  "3_localisation_et_cadre": {
    "accessibilite_et_bruit": "string (obligatoire : transports, route, bruit)",
    "zone_affectation_projets": "string",
    "fiscalite_communale": "string (comparer aux 69,4 pts de moyenne cantonale VD)",
    "compatibilite_criteres_utilisateur": "string"
  },
  "4_lecture_critique": [
    {"formulation_vendeur": "string (sans chevrons ni guillemets autour)", "realite_terrain": "string"}
  ],
  "5_copropriete_et_batiment": {
    "points_favorables": ["string"],
    "points_a_instruire": ["string"],
    "energie_et_calendrier_legal": "string (DACCE 2033, LVLEne fév. 2026 seuil 750 m2 SRE, loi VS 2025, coûts travaux PAC/fenêtres)"
  },
  "6_valorisation": {
    "prix_m2_annonce": "string",
    "prix_m2_recalcule": "string (surface réelle chauffée, pondérée, part de circulation)",
    "comparables_estimes": [{"description": "string (avec surface et prix annexes comprises)", "prix_m2": "string"}],
    "grille_ajustement": [
      {"poste": "string", "scenario_a": "string", "scenario_b": "string", "justification": "string"}
    ],
    "test_rendement_locatif": "string"
  },
  "7_matrice_risques": [
    {
      "numero": 1,
      "risque": "string",
      "gravite": "Faible | Moyenne | Elevée",
      "probabilite": "Faible | Moyenne | Forte",
      "impact_chiffre": "string",
      "qui_peut_lever_le_doute": "string"
    }
  ],
  "8_strategie_offre": {
    "sequence_demarches": ["string"],
    "arguments_negociation_par_poids": ["string"],
    "atouts_vendeur": ["string"]
  },
  "9_couts_acquisition_detention": {
    "frais_acquisition_cibles": "string (mutation, notaire, RF, cédule ~3000 CHF)",
    "cout_total_entree": "string",
    "cout_detention_annuel_reel": "string (taux effectif 1,5-2,0 %, distinct de la charge bancaire à 5 %)"
  },
  "10_financement": {
    "tableau_financement": [
      {"poste": "Prix d'acquisition (parkings inclus)", "prix_demande": "string", "prix_cible": "string"},
      {"poste": "Fonds propres 20 % + Frais (~4,5 % + cédule)", "prix_demande": "string", "prix_cible": "string"},
      {"poste": "Prêt 80 % (1er rang 65 % / 2e rang 15 %)", "prix_demande": "string", "prix_cible": "string"},
      {"poste": "Amortissement annuel 2e rang (sur 15 ans)", "prix_demande": "string", "prix_cible": "string"},
      {"poste": "Charge théorique bancaire (5 % + 1 % + amort.)", "prix_demande": "string", "prix_cible": "string"},
      {"poste": "Revenu brut annuel requis (tenue à 33 %)", "prix_demande": "string", "prix_cible": "string"}
    ],
    "hypotheses_prix_demande": "string",
    "hypotheses_prix_cible": "string",
    "composition_fonds_propres": "string (10 % durs min incluant 3a, retrait vs mise en gage 2e pilier, ou 30-40 % si secondaire)",
    "modalites_amortissement_2e_rang": "string (confronter obligatoirement aux plafonds 3a 2026 : 7'258 CHF / 14'516 CHF couple / 36'288 CHF indép.)"
  },
  "11_fiscalite": {
    "taux_communal_et_comparaison": "string (points communaux vs moyenne cantonale 69,4 pts et communes voisines)",
    "impact_impot_foncier": "string (1,0 à 1,5 pour mille de l'estimation fiscale)",
    "forfait_entretien_et_economie_3a": "string (forfait VD 20 % / 30 % jusqu'à fin 2028 + économie d'impôt 3a)",
    "impact_suppression_valeur_locative_2029": "string (suppression au 01.01.2029, calendrier des travaux avant fin 2028, déduction primo-acquéreurs 10 ans)"
  },
  "annexe_a_documents_a_reclamer": [
    {"document": "string (inclure toujours l'estimation fiscale du lot)", "permet_de_trancher": "string", "numero_risque_lie": 1}
  ],
  "annexe_b_points_visite": [
    {"point_a_verifier_sur_place": "string"}
  ],
  "conclusion": {
    "constats_decisifs": ["string (4 à 6 constats décisifs)"],
    "sources_consultees": ["string (sources et références consultées)"]
  }
}
"""

# --- TEMPLATE HTML IDENTIQUE AU RENDU DE RAPPORT_ANALYSE_IMMO-V2 ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8">
    <style>
        @page {
            size: A4;
            margin: 12mm 14mm 14mm 14mm;
            @bottom-right {
                content: "Page " counter(page) " / " counter(pages);
                font-family: 'Helvetica', Arial, sans-serif;
                font-size: 8pt;
                color: #718096;
            }
            @bottom-left {
                content: "Note d'analyse d'acquisition — Suisse romande";
                font-family: 'Helvetica', Arial, sans-serif;
                font-size: 8pt;
                color: #718096;
            }
        }
        body { font-family: 'Georgia', serif; font-size: 9.5pt; color: #222; line-height: 1.38; margin: 0; }
        h1, h2, h3, th { font-family: 'Helvetica', Arial, sans-serif; color: #13294b; page-break-after: avoid; break-after: avoid; }
        h1 { border-bottom: 2px solid #1f5fa8; padding-bottom: 5px; font-size: 20px; margin-top: 0; margin-bottom: 10px; }
        h2 { color: #13294b; border-left: 4px solid #1f5fa8; background-color: #f6f9fc; padding: 4px 8px; font-size: 13px; margin-top: 14px; margin-bottom: 6px; }
        h3 { color: #1f5fa8; font-size: 11px; margin-top: 8px; margin-bottom: 4px; }

        table { width: 100%; border-collapse: collapse; margin-bottom: 10px; page-break-inside: auto; break-inside: auto; font-family: 'Helvetica', Arial, sans-serif; }
        thead { display: table-header-group; }
        tr { page-break-inside: avoid; break-inside: avoid; }
        th, td { padding: 5px 7px; text-align: left; border: 1px solid #cbd5e1; font-size: 8.8pt; vertical-align: top; overflow-wrap: break-word; }
        th { background-color: #13294b; color: white; }
        tbody tr:nth-child(even) { background-color: #f6f9fc; }
        tbody tr:nth-child(odd) { background-color: #ffffff; }
        .row-highlight { background-color: #e3ebf6 !important; }

        .encadre-verdict { border: 1.5px solid #1f5fa8; background-color: #e3ebf6; padding: 10px 12px; border-radius: 4px; margin-bottom: 10px; page-break-inside: avoid; break-inside: avoid; }
        .encadre-alerte { border-left: 4px solid #e53e3e; background-color: #fff5f5; padding: 8px 12px; margin-bottom: 10px; page-break-inside: avoid; break-inside: avoid; }
        .encadre-warning { border-left: 4px solid #dd6b20; background-color: #fffaf0; padding: 8px 12px; margin-bottom: 10px; page-break-inside: avoid; break-inside: avoid; }
        .encadre-etape { border-left: 4px solid #1f5fa8; background-color: #f6f9fc; padding: 8px 12px; margin-bottom: 10px; font-family: 'Helvetica', sans-serif; font-size: 9pt; page-break-inside: avoid; break-inside: avoid; }

        /* Badges de fiabilité A (gris), E (orange), V (bleu) */
        .badge-rel { display: inline-block; padding: 0px 4px; border-radius: 3px; font-family: 'Helvetica', sans-serif; font-size: 7.5pt; font-weight: bold; color: white; }
        .badge-A { background-color: #718096; }
        .badge-E { background-color: #dd6b20; }
        .badge-V { background-color: #1f5fa8; }

        /* Badges de gravité des risques */
        .badge-Faible { background-color: #1f5fa8; color: white; padding: 2px 6px; border-radius: 4px; font-size: 8pt; font-family: sans-serif; font-weight: bold; }
        .badge-Moyenne { background-color: #dd6b20; color: white; padding: 2px 6px; border-radius: 4px; font-size: 8pt; font-family: sans-serif; font-weight: bold; }
        .badge-Elevée, .badge-Élevée { background-color: #e53e3e; color: white; padding: 2px 6px; border-radius: 4px; font-size: 8pt; font-family: sans-serif; font-weight: bold; }

        ul { margin-top: 4px; margin-bottom: 8px; padding-left: 18px; }
        ul.checklist { list-style-type: none; padding-left: 4px; }
        li { margin-bottom: 3px; }
        .avertissement { font-size: 7.8pt; color: #718096; text-align: justify; margin-top: 16px; border-top: 1px solid #cbd5e1; padding-top: 6px; page-break-inside: avoid; break-inside: avoid; }
    </style>
</head>
<body>
    <h1>Note d'analyse d'acquisition</h1>

    <h2>1. Synthèse et verdict</h2>
    <div class="encadre-verdict">
        <strong>Verdict :</strong> {{ data['1_synthese_et_verdict'].verdict_conditionnel | format_badges | safe }}
    </div>

    <table>
        <thead>
            <tr>
                <th style="width: 18%;">Scénario</th>
                <th style="width: 34%;">Valeur estimée</th>
                <th style="width: 24%;">Offre d'ouverture</th>
                <th style="width: 24%;">Prix plafond</th>
            </tr>
        </thead>
        <tbody>
            {% for sc in data['1_synthese_et_verdict'].scenarios %}
            <tr>
                <td><strong>{{ sc.type }}</strong></td>
                <td>{{ sc.valeur_estimee_fourchette | format_badges | safe }}</td>
                <td>{{ sc.offre_ouverture | format_badges | safe }}</td>
                <td>{{ sc.prix_plafond | format_badges | safe }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <div class="encadre-alerte">
        <strong>⚠️ Les quatre alertes :</strong>
        <ul>
            {% for alerte in data['1_synthese_et_verdict'].quatre_alertes %}
            <li>{{ alerte | format_badges | safe }}</li>
            {% endfor %}
        </ul>
    </div>

    <div class="encadre-etape">
        <strong>Prochaine étape :</strong> {{ data['1_synthese_et_verdict'].prochaine_etape | format_badges | safe }}
    </div>

    <h2>2. Identification du bien</h2>
    <table>
        <thead>
            <tr>
                <th style="width: 28%;">Caractéristique</th>
                <th style="width: 72%;">Valeur &amp; Fiabilité</th>
            </tr>
        </thead>
        <tbody>
            {% for car in data['2_identification_bien'].caracteristiques %}
            <tr>
                <td><strong>{{ car.cle }}</strong></td>
                <td>{{ car.valeur_et_fiabilite | format_badges | safe }}</td>
            </tr>
            {% endfor %}
            <tr class="row-highlight">
                <td><strong>Données manquantes</strong></td>
                <td>{{ data['2_identification_bien'].donnees_manquantes | join(' · ') | format_badges | safe }}</td>
            </tr>
        </tbody>
    </table>

    <h2>3. Localisation et cadre réglementaire</h2>
    <ul>
        <li><strong>Accessibilité &amp; Bruit :</strong> {{ data['3_localisation_et_cadre'].accessibilite_et_bruit | format_badges | safe }}</li>
        <li><strong>Zone &amp; Projets :</strong> {{ data['3_localisation_et_cadre'].zone_affectation_projets | format_badges | safe }}</li>
        <li><strong>Fiscalité communale :</strong> {{ data['3_localisation_et_cadre'].fiscalite_communale | format_badges | safe }}</li>
        <li><strong>Observations :</strong> {{ data['3_localisation_et_cadre'].compatibilite_criteres_utilisateur | format_badges | safe }}</li>
    </ul>

    <h2>4. Lecture critique de la documentation</h2>
    <table>
        <thead>
            <tr>
                <th style="width: 32%;">Formulation du vendeur</th>
                <th style="width: 68%;">Ce qu'elle signifie réellement</th>
            </tr>
        </thead>
        <tbody>
            {% for ligne in data['4_lecture_critique'] %}
            <tr>
                <td><em>« {{ ligne.formulation_vendeur | clean_quotes }} »</em></td>
                <td>{{ ligne.realite_terrain | format_badges | safe }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <h2>5. Copropriété et bâtiment</h2>
    <ul>
        <li><strong>Ce qui est favorable :</strong> {{ data['5_copropriete_et_batiment'].points_favorables | join(' / ') | format_badges | safe }}</li>
        <li><strong>Ce qu'il faut instruire :</strong> {{ data['5_copropriete_et_batiment'].points_a_instruire | join(' / ') | format_badges | safe }}</li>
    </ul>
    <div class="encadre-warning">
        <strong>⚡ Énergie &amp; Calendrier légal :</strong> {{ data['5_copropriete_et_batiment'].energie_et_calendrier_legal | format_badges | safe }}
    </div>

    <h2>6. Valorisation</h2>
    <ul>
        <li><strong>Prix annoncé :</strong> {{ data['6_valorisation'].prix_m2_annonce | format_badges | safe }}</li>
        <li><strong>Prix recalculé (surface réelle) :</strong> <strong>{{ data['6_valorisation'].prix_m2_recalcule | format_badges | safe }}</strong></li>
        <li><strong>Rendement locatif estimé :</strong> {{ data['6_valorisation'].test_rendement_locatif | format_badges | safe }}</li>
    </ul>

    {% if data['6_valorisation'].comparables_estimes %}
    <table>
        <thead>
            <tr>
                <th style="width: 68%;">Comparable (Marché)</th>
                <th style="width: 32%;">Prix estimé / m²</th>
            </tr>
        </thead>
        <tbody>
            {% for comp in data['6_valorisation'].comparables_estimes %}
            <tr>
                <td>{{ comp.description | format_badges | safe }}</td>
                <td>{{ comp.prix_m2 | format_badges | safe }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% endif %}

    {% if data['6_valorisation'].get('grille_ajustement') %}
    <h3>Grille d'ajustement transparente (Scénarios A et B)</h3>
    <table>
        <thead>
            <tr>
                <th style="width: 28%;">Poste</th>
                <th style="width: 18%;">Scénario A</th>
                <th style="width: 18%;">Scénario B</th>
                <th style="width: 36%;">Justification</th>
            </tr>
        </thead>
        <tbody>
            {% for adj in data['6_valorisation'].grille_ajustement %}
            <tr>
                <td><strong>{{ adj.poste }}</strong></td>
                <td>{{ adj.scenario_a | format_badges | safe }}</td>
                <td>{{ adj.scenario_b | format_badges | safe }}</td>
                <td>{{ adj.justification | format_badges | safe }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% endif %}

    <h2>7. Matrice des risques</h2>
    <table>
        <thead>
            <tr>
                <th style="width: 5%;">N°</th>
                <th style="width: 31%;">Risque</th>
                <th style="width: 11%;">Gravité</th>
                <th style="width: 11%;">Probabilité</th>
                <th style="width: 22%;">Impact</th>
                <th style="width: 20%;">Qui peut lever le doute</th>
            </tr>
        </thead>
        <tbody>
            {% for risque in data['7_matrice_risques'] %}
            <tr>
                <td><strong>{{ risque.numero }}</strong></td>
                <td>{{ risque.risque | format_badges | safe }}</td>
                <td><span class="badge-{{ risque.gravite }}">{{ risque.gravite }}</span></td>
                <td>{{ risque.probabilite }}</td>
                <td>{{ risque.impact_chiffre | format_badges | safe }}</td>
                <td>{{ risque.qui_peut_lever_le_doute | format_badges | safe }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <h2>8. Stratégie d'offre</h2>
    <ul>
        <li><strong>Démarches :</strong> {{ data['8_strategie_offre'].sequence_demarches | join(' ➔ ') | format_badges | safe }}</li>
        <li><strong>Arguments de négociation :</strong> {{ data['8_strategie_offre'].arguments_negociation_par_poids | join(' | ') | format_badges | safe }}</li>
        <li><strong>Atouts vendeur :</strong> {{ data['8_strategie_offre'].atouts_vendeur | join(' | ') | format_badges | safe }}</li>
    </ul>

    <h2>9. Coûts d'acquisition &amp; 10. Financement</h2>
    <ul>
        <li><strong>Frais d'acquisition :</strong> {{ data['9_couts_acquisition_detention'].frais_acquisition_cibles | format_badges | safe }}</li>
        <li><strong>Coût total d'entrée :</strong> {{ data['9_couts_acquisition_detention'].cout_total_entree | format_badges | safe }}</li>
        <li><strong>Coût de détention annuel réel :</strong> {{ data['9_couts_acquisition_detention'].cout_detention_annuel_reel | format_badges | safe }}</li>
    </ul>

    {% if data['10_financement'].get('tableau_financement') %}
    <table>
        <thead>
            <tr>
                <th style="width: 40%;">Poste de financement</th>
                <th style="width: 30%;">Au prix demandé</th>
                <th style="width: 30%;">Au prix cible</th>
            </tr>
        </thead>
        <tbody>
            {% for row in data['10_financement'].tableau_financement %}
            <tr>
                <td><strong>{{ row.poste }}</strong></td>
                <td>{{ row.prix_demande | format_badges | safe }}</td>
                <td>{{ row.prix_cible | format_badges | safe }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <ul>
        <li><strong>Financement (prix demandé) :</strong> {{ data['10_financement'].hypotheses_prix_demande | format_badges | safe }}</li>
        <li><strong>Financement (prix cible) :</strong> {{ data['10_financement'].hypotheses_prix_cible | format_badges | safe }}</li>
    </ul>
    {% endif %}

    <ul>
        <li><strong>Composition des fonds propres :</strong> {{ data['10_financement'].composition_fonds_propres | format_badges | safe }}</li>
        <li><strong>Modalités d'amortissement du 2e rang (plafonds 3a 2026) :</strong> {{ data['10_financement'].modalites_amortissement_2e_rang | format_badges | safe }}</li>
    </ul>

    <h2>11. Fiscalité</h2>
    <ul>
        {% if data['11_fiscalite'].get('taux_communal_et_comparaison') and data['11_fiscalite'].get('taux_communal_et_comparaison') != 'Non mentionné' %}
        <li><strong>Taux communal (vs moyenne cantonale 69,4 pts) :</strong> {{ data['11_fiscalite'].taux_communal_et_comparaison | format_badges | safe }}</li>
        {% endif %}
        <li><strong>Impôt foncier :</strong> {{ data['11_fiscalite'].impact_impot_foncier | format_badges | safe }}</li>
        {% if data['11_fiscalite'].get('forfait_entretien_et_economie_3a') and data['11_fiscalite'].get('forfait_entretien_et_economie_3a') != 'Non mentionné' %}
        <li><strong>Forfait d'entretien &amp; Économie 3a :</strong> {{ data['11_fiscalite'].forfait_entretien_et_economie_3a | format_badges | safe }}</li>
        {% endif %}
        <li><strong>Suppression de la valeur locative (2029) &amp; Calendrier travaux :</strong> {{ data['11_fiscalite'].impact_suppression_valeur_locative_2029 | format_badges | safe }}</li>
    </ul>

    <h2>Annexes</h2>
    <table>
        <thead>
            <tr>
                <th colspan="3">Annexe A — Documents à réclamer</th>
            </tr>
            <tr class="row-highlight">
                <td style="width: 38%;"><strong>Document</strong></td>
                <td style="width: 50%;"><strong>Permet de trancher</strong></td>
                <td style="width: 12%;"><strong>Risque lié</strong></td>
            </tr>
        </thead>
        <tbody>
            {% for doc in data['annexe_a_documents_a_reclamer'] %}
            <tr>
                <td>{{ doc.document | format_badges | safe }}</td>
                <td>{{ doc.permet_de_trancher | format_badges | safe }}</td>
                <td>N°{{ doc.numero_risque_lie }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <p><strong>Annexe B — Points de visite spécifiques :</strong></p>
    <ul class="checklist">
        {% for point in data['annexe_b_points_visite'] %}
        <li>☐ {{ point.point_a_verifier_sur_place | format_badges | safe }}</li>
        {% endfor %}
    </ul>

    {% if data.get('conclusion') and data['conclusion'].get('constats_decisifs') %}
    <h2>Synthèse des constats décisifs &amp; Sources</h2>
    <div class="encadre-verdict">
        <strong>Constats décisifs :</strong>
        <ul>
            {% for constat in data['conclusion'].constats_decisifs %}
            <li>{{ constat | format_badges | safe }}</li>
            {% endfor %}
        </ul>
    </div>
    {% if data['conclusion'].get('sources_consultees') %}
    <p style="font-size: 8.5pt; color: #4a5568;">
        <strong>Sources consultées :</strong> {{ data['conclusion'].sources_consultees | join(' · ') }}
    </p>
    {% endif %}
    {% endif %}

    <div class="avertissement">
        <strong>Avertissement :</strong> Cette note d'analyse pré-acquisition distingue les données déclaratives non vérifiées <span class="badge-rel badge-A">A</span>, les estimations de l'analyste <span class="badge-rel badge-E">E</span> et les éléments établis par une pièce au dossier <span class="badge-rel badge-V">V</span>. Elle ne constitue ni un conseil en investissement, ni un avis juridique ou fiscal.
    </div>
</body>
</html>
"""

# --- INTERFACE PRINCIPALE ÉPURÉE ---
mode_test_selectionne = modele_choisi.startswith("🧪")
uploaded_file = st.file_uploader("Déposez la plaquette commerciale (PDF)", type="pdf")

if uploaded_file or mode_test_selectionne:
    if st.button("Lancer l'analyse 🚀"):
        with st.spinner("Claude examine le document et les plans... (cela peut prendre quelques minutes)"):
            try:
                # CAS A : Mode Test Gratuit (0 crédit consommé)
                if mode_test_selectionne:
                    fichiers_cache = sorted(CACHE_DIR.glob("*.json"), key=os.path.getmtime, reverse=True)
                    donnees = None
                    for fc in fichiers_cache:
                        candidat = normaliser_et_fusionner(json.loads(fc.read_text(encoding="utf-8")))
                        if est_analyse_complete(candidat):
                            donnees = candidat
                            info_cout = f"Mode Test Gratuit — chargé depuis votre cache complet ({fc.name}), 0 crédit utilisé"
                            break
                    if donnees is None:
                        donnees = normaliser_et_fusionner(DONNEES_DEMO_TEST)
                        info_cout = "Mode Test Gratuit — données de démonstration complètes utilisées, 0 crédit utilisé"

                # CAS B : Analyse d'un PDF avec cache intelligent + Prompt Caching Anthropic
                else:
                    pdf_bytes_input = uploaded_file.read()
                    file_hash = hashlib.sha256(pdf_bytes_input).hexdigest()[:16]
                    fichier_cache_local = CACHE_DIR / f"{file_hash}.json"

                    donnees = None
                    # Si la case "Activer le cache intelligent" est cochée et qu'un cache COMPLET existe
                    if utiliser_cache and fichier_cache_local.exists():
                        candidat = normaliser_et_fusionner(json.loads(fichier_cache_local.read_text(encoding="utf-8")))
                        if est_analyse_complete(candidat):
                            donnees = candidat
                            info_cout = "Chargé depuis le cache intelligent (0 crédit utilisé)"
                        else:
                            # Suppression automatique d'un ancien cache incomplet/tronqué
                            fichier_cache_local.unlink(missing_ok=True)

                    if donnees is None:
                        pdf_base64 = base64.b64encode(pdf_bytes_input).decode("utf-8")

                        # max_tokens=32000 indispensable pour que le ThinkingBlock ne tronque jamais la fin du JSON
                        with client.messages.stream(
                            model=modele_choisi,
                            max_tokens=32000,
                            system=[
                                {
                                    "type": "text",
                                    "text": SYSTEM_PROMPT,
                                    "cache_control": {"type": "ephemeral"}
                                }
                            ],
                            messages=[{
                                "role": "user",
                                "content": [
                                    {
                                        "type": "document",
                                        "source": {
                                            "type": "base64",
                                            "media_type": "application/pdf",
                                            "data": pdf_base64
                                        },
                                        "cache_control": {"type": "ephemeral"}
                                    },
                                    {
                                        "type": "text",
                                        "text": (
                                            "Analyse ce document et renvoie uniquement l'objet JSON valide commençant par { et finissant par }. "
                                            "Remplis impérativement TOUTES les sections de 1 à 11 (y compris accessibilite_et_bruit, grille_ajustement, "
                                            "tableau_financement, les 4 points de fiscalité, les annexes A et B et la conclusion). "
                                            "Reste synthétique dans chaque champ (2 à 3 phrases max) pour que le JSON soit 100 % complet, "
                                            "et n'utilise jamais de guillemets droits (\") dans tes phrases."
                                        )
                                    }
                                ]
                            }]
                        ) as stream:
                            response = stream.get_final_message()

                        donnees = extraire_donnees_claude(response)

                        # On ne sauvegarde dans le cache que si l'analyse est complète (non tronquée)
                        if utiliser_cache and est_analyse_complete(donnees):
                            fichier_cache_local.write_text(
                                json.dumps(donnees, ensure_ascii=False, indent=2),
                                encoding="utf-8"
                            )
                        info_cout = f"Analyse complète effectuée avec {modele_choisi}"

                # 4. Génération du PDF avec WeasyPrint
                rendered_html = rendre_html_avec_filtres(HTML_TEMPLATE, donnees)
                pdf_bytes = HTML(string=rendered_html).write_pdf()

                # 5. Téléchargement
                st.success(f"✅ Analyse terminée ! ({info_cout})")
                st.download_button(
                    label="📥 Télécharger le Rapport PDF",
                    data=pdf_bytes,
                    file_name="Rapport_Analyse_Immo.pdf",
                    mime="application/pdf"
                )

            except Exception as e:
                st.error(f"Une erreur s'est produite : {e}")
