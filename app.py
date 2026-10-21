import streamlit as st
import anthropic
import base64
import json
import re
from jinja2 import Template
from weasyprint import HTML

st.set_page_config(page_title="Due Diligence Immo Suisse", page_icon="🏢", layout="centered")
st.title("🇨🇭 Analyse Due Diligence Immobilier (Suisse Romande)")

# Récupération sécurisée de la clé API
if "ANTHROPIC_API_KEY" not in st.secrets:
    st.error("Clé ANTHROPIC_API_KEY introuvable dans les Secrets Streamlit.")
    st.stop()

api_key = st.secrets["ANTHROPIC_API_KEY"]
client = anthropic.Anthropic(api_key=api_key)

# --- DÉTECTION AUTOMATIQUE DES MODÈLES ACTIFS ---
@st.cache_data(ttl=3600)
def charger_modeles_actifs(_api_key):
    c = anthropic.Anthropic(api_key=_api_key)
    liste = [m.id for m in c.models.list().data]
    # On place les modèles Sonnet en tête de liste
    sonnets = [m for m in liste if "sonnet" in m.lower()]
    autres = [m for m in liste if "sonnet" not in m.lower()]
    return sonnets + autres

try:
    modeles_disponibles = charger_modeles_actifs(api_key)
    modele_choisi = st.selectbox(
        "Modèle Claude actif détecté sur votre compte :",
        options=modeles_disponibles,
        index=0
    )
except Exception as e:
    st.error(f"Impossible de lister les modèles Anthropic. Vérifiez votre clé API : {e}")
    st.stop()

# --- PROMPT SYSTÈME SUISSE ROMANDE ---
SYSTEM_PROMPT = """
# RÔLE ET EXPERTISE
Tu es un analyste immobilier senior, spécialisé dans la due diligence pré-acquisition en Suisse romande. L'utilisateur te fournit la documentation de vente d'un bien (plaquette, plans, CECB, etc.). Ta mission est de produire une note d'analyse d'acquisition exhaustive et critique en français.

# MÉTHODOLOGIE (À APPLIQUER STRICTEMENT)
1. Analyse documentaire : Lis toute la documentation, y compris plans, CECB et annexes graphiques. Les plans priment systématiquement sur le texte commercial.
2. Confrontation :
   - Additionne les surfaces cotées des pièces et compare à la surface annoncée.
   - Distingue surface habitable chauffée, surface PPE brute, surface pondérée, balcons, vérandas non chauffées et locaux non habitables.
   - Vérifie la cohérence du nombre de chambres avec le nombre de pièces annoncé.
   - Relève tout écart entre le texte et les plans, et repère les locaux livrés bruts ou annexes non autorisées.
3. Données de marché et légales :
   - Évalue le prix au m² moyen/médian de la commune, 3 à 5 comparables estimés, et le loyer de marché au m² pour le test de rendement.
   - Applique le cadre légal énergétique cantonal (décret vaudois DACCE, LVLEne et seuil des 750 m² SRE, loi valaisanne sur l'énergie, etc.) et le taux d'imposition communal.
4. Fiabilité des données :
   Marque chaque donnée : [A] = annoncé par le vendeur, non vérifié ; [E] = estimation ou hypothèse de l'analyste ; [V] = établi par une pièce au dossier. N'invente jamais une donnée absente : écris qu'elle manque et range-la dans les documents à réclamer.

# HYPOTHÈSES DE CALCUL STANDARD
- Charge théorique : taux calculatoire 5 %, entretien 1 %, amortissement du 2e rang sur 15 ans jusqu'à 65 % de la valeur, tenue à 33 % du revenu brut.
- Frais d'acquisition : Vaud ~4,5 % (mutation 3,3 %, notaire et RF ~1,2 %) ; Valais ~2,5 % (mutation 1,5 %, RF 0,2 %, notaire 0,5-0,7 %). Applicables aussi aux places de parc vendues séparément.
- Coût de détention réel : taux effectif 1,5 à 2,0 %, distinct du taux calculatoire.
- Financement : 10 % de fonds propres durs minimum, retrait anticipé vs mise en gage 2e pilier, amortissement direct vs indirect via 3e pilier A. Si résidence secondaire : pas de 2e pilier, 30-40 % de fonds propres.

# FORMAT DE RÉPONSE EXIGÉ
Réponds UNIQUEMENT avec un objet JSON valide (sans balises markdown avant ou après) respectant exactement cette structure :
{
  "1_synthese_et_verdict": {
    "verdict_conditionnel": "string",
    "scenarios": [
      {
        "type": "A favorable | B dégradé | C risque spécifique",
        "valeur_estimee_fourchette": "string",
        "offre_ouverture": "string",
        "prix_plafond": "string"
      }
    ],
    "quatre_alertes": ["string"],
    "prochaine_etape": "string"
  },
  "2_identification_bien": {
    "caracteristiques": [{"cle": "string", "valeur_et_fiabilite": "string"}],
    "donnees_manquantes": ["string"]
  },
  "3_localisation_et_cadre": {
    "accessibilite_et_bruit": "string",
    "zone_affectation_projets": "string",
    "fiscalite_communale": "string",
    "compatibilite_criteres_utilisateur": "string"
  },
  "4_lecture_critique": [
    {"formulation_vendeur": "string", "realite_terrain": "string"}
  ],
  "5_copropriete_et_batiment": {
    "points_favorables": ["string"],
    "points_a_instruire": ["string"],
    "energie_et_calendrier_legal": "string"
  },
  "6_valorisation": {
    "prix_m2_annonce": "string",
    "prix_m2_recalcule": "string",
    "comparables_estimes": [{"description": "string", "prix_m2": "string"}],
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
    "frais_acquisition_cibles": "string",
    "cout_total_entree": "string",
    "cout_detention_annuel_reel": "string"
  },
  "10_financement": {
    "hypotheses_prix_demande": "string",
    "hypotheses_prix_cible": "string",
    "composition_fonds_propres": "string",
    "modalites_amortissement_2e_rang": "string"
  },
  "11_fiscalite": {
    "impact_impot_foncier": "string",
    "impact_suppression_valeur_locative_2029": "string"
  },
  "annexe_a_documents_a_reclamer": [
    {"document": "string", "permet_de_trancher": "string", "numero_risque_lie": 1}
  ],
  "annexe_b_points_visite": [
    {"point_a_verifier_sur_place": "string"}
  ]
}
"""

# --- TEMPLATE HTML CHARTE BLEUE ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8">
    <style>
        @page { size: A4; margin: 15mm; }
        body { font-family: 'Georgia', serif; font-size: 10.5pt; color: #333; line-height: 1.45; }
        h1, h2, h3, th { font-family: 'Helvetica', Arial, sans-serif; color: #13294b; page-break-after: avoid; }
        h1 { border-bottom: 2px solid #1f5fa8; padding-bottom: 6px; font-size: 22px; }
        h2 { color: #1f5fa8; font-size: 15px; margin-top: 22px; border-bottom: 1px solid #e3ebf6; padding-bottom: 3px; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 14px; page-break-inside: avoid; }
        th, td { padding: 7px 8px; text-align: left; border: 1px solid #e3ebf6; font-size: 9.5pt; vertical-align: top; }
        th { background-color: #13294b; color: white; }
        tr:nth-child(even) { background-color: #f6f9fc; }
        tr:nth-child(odd) { background-color: #ffffff; }
        .encadre-verdict { border: 2px solid #1f5fa8; background-color: #f6f9fc; padding: 14px; border-radius: 5px; margin-bottom: 14px; }
        .encadre-alerte { border-left: 5px solid #e53e3e; background-color: #fff5f5; padding: 10px 15px; margin-bottom: 14px; }
        .encadre-etape { border-left: 5px solid #1f5fa8; background-color: #e3ebf6; padding: 10px 15px; margin-bottom: 14px; font-family: 'Helvetica', sans-serif; }
        .badge-Faible { background-color: #3182ce; color: white; padding: 2px 6px; border-radius: 4px; font-size: 8.5pt; font-family: sans-serif; }
        .badge-Moyenne { background-color: #dd6b20; color: white; padding: 2px 6px; border-radius: 4px; font-size: 8.5pt; font-family: sans-serif; }
        .badge-Elevée { background-color: #e53e3e; color: white; padding: 2px 6px; border-radius: 4px; font-size: 8.5pt; font-family: sans-serif; }
        ul { margin-top: 5px; padding-left: 20px; }
        li { margin-bottom: 4px; }
        .avertissement { font-size: 8pt; color: #718096; text-align: justify; margin-top: 35px; border-top: 1px solid #e2e8f0; padding-top: 10px; }
    </style>
</head>
<body>
    <h1>Note d'analyse d'acquisition</h1>

    <h2>1. Synthèse et verdict</h2>
    <div class="encadre-verdict">
        <strong>Verdict :</strong> {{ data['1_synthese_et_verdict'].verdict_conditionnel }}
    </div>

    <table>
        <tr>
            <th>Scénario</th>
            <th>Valeur estimée</th>
            <th>Offre d'ouverture</th>
            <th>Prix plafond</th>
        </tr>
        {% for sc in data['1_synthese_et_verdict'].scenarios %}
        <tr>
            <td><strong>{{ sc.type }}</strong></td>
            <td>{{ sc.valeur_estimee_fourchette }}</td>
            <td>{{ sc.offre_ouverture }}</td>
            <td>{{ sc.prix_plafond }}</td>
        </tr>
        {% endfor %}
    </table>

    <div class="encadre-alerte">
        <strong>⚠️ Les quatre alertes :</strong>
        <ul>
            {% for alerte in data['1_synthese_et_verdict'].quatre_alertes %}
            <li>{{ alerte }}</li>
            {% endfor %}
        </ul>
    </div>

    <div class="encadre-etape">
        <strong>Prochaine étape :</strong> {{ data['1_synthese_et_verdict'].prochaine_etape }}
    </div>

    <h2>2. Identification du bien</h2>
    <table>
        <tr>
            <th>Caractéristique</th>
            <th>Valeur & Fiabilité</th>
        </tr>
        {% for car in data['2_identification_bien'].caracteristiques %}
        <tr>
            <td>{{ car.cle }}</td>
            <td>{{ car.valeur_et_fiabilite }}</td>
        </tr>
        {% endfor %}
        <tr>
            <td><strong>Données manquantes</strong></td>
            <td>{{ data['2_identification_bien'].donnees_manquantes | join(', ') }}</td>
        </tr>
    </table>

    <h2>3. Localisation et cadre réglementaire</h2>
    <ul>
        <li><strong>Accessibilité & Bruit :</strong> {{ data['3_localisation_et_cadre'].accessibilite_et_bruit }}</li>
        <li><strong>Zone & Projets :</strong> {{ data['3_localisation_et_cadre'].zone_affectation_projets }}</li>
        <li><strong>Fiscalité :</strong> {{ data['3_localisation_et_cadre'].fiscalite_communale }}</li>
        <li><strong>Compatibilité :</strong> {{ data['3_localisation_et_cadre'].compatibilite_criteres_utilisateur }}</li>
    </ul>

    <h2>4. Lecture critique de la documentation</h2>
    <table>
        <tr>
            <th>Formulation du vendeur</th>
            <th>Ce qu'elle signifie réellement</th>
        </tr>
        {% for ligne in data['4_lecture_critique'] %}
        <tr>
            <td><em>"{{ ligne.formulation_vendeur }}"</em></td>
            <td>{{ ligne.realite_terrain }}</td>
        </tr>
        {% endfor %}
    </table>

    <h2>5. Copropriété et bâtiment</h2>
    <ul>
        <li><strong>Points favorables :</strong> {{ data['5_copropriete_et_batiment'].points_favorables | join(' / ') }}</li>
        <li><strong>À instruire :</strong> {{ data['5_copropriete_et_batiment'].points_a_instruire | join(' / ') }}</li>
        <li><strong>Énergie & Légal :</strong> {{ data['5_copropriete_et_batiment'].energie_et_calendrier_legal }}</li>
    </ul>

    <h2>6. Valorisation</h2>
    <ul>
        <li><strong>Prix annoncé :</strong> {{ data['6_valorisation'].prix_m2_annonce }}</li>
        <li><strong>Prix recalculé (surface réelle) :</strong> <strong>{{ data['6_valorisation'].prix_m2_recalcule }}</strong></li>
        <li><strong>Rendement locatif estimé :</strong> {{ data['6_valorisation'].test_rendement_locatif }}</li>
    </ul>

    {% if data['6_valorisation'].comparables_estimes %}
    <table>
        <tr>
            <th>Comparable (Marché)</th>
            <th>Prix estimé / m²</th>
        </tr>
        {% for comp in data['6_valorisation'].comparables_estimes %}
        <tr>
            <td>{{ comp.description }}</td>
            <td>{{ comp.prix_m2 }}</td>
        </tr>
        {% endfor %}
    </table>
    {% endif %}

    <h2>7. Matrice des risques</h2>
    <table>
        <tr>
            <th>N°</th>
            <th>Risque</th>
            <th>Gravité</th>
            <th>Probabilité</th>
            <th>Impact</th>
            <th>Action</th>
        </tr>
        {% for risque in data['7_matrice_risques'] %}
        <tr>
            <td>{{ risque.numero }}</td>
            <td>{{ risque.risque }}</td>
            <td><span class="badge-{{ risque.gravite }}">{{ risque.gravite }}</span></td>
            <td>{{ risque.probabilite }}</td>
            <td>{{ risque.impact_chiffre }}</td>
            <td>{{ risque.qui_peut_lever_le_doute }}</td>
        </tr>
        {% endfor %}
    </table>

    <h2>8. Stratégie d'offre</h2>
    <ul>
        <li><strong>Démarches :</strong> {{ data['8_strategie_offre'].sequence_demarches | join(' ➔ ') }}</li>
        <li><strong>Arguments de négociation :</strong> {{ data['8_strategie_offre'].arguments_negociation_par_poids | join(' | ') }}</li>
        <li><strong>Atouts vendeur :</strong> {{ data['8_strategie_offre'].atouts_vendeur | join(' | ') }}</li>
    </ul>

    <h2>9. Coûts d'acquisition & 10. Financement</h2>
    <ul>
        <li><strong>Frais d'acquisition :</strong> {{ data['9_couts_acquisition_detention'].frais_acquisition_cibles }}</li>
        <li><strong>Coût total d'entrée :</strong> {{ data['9_couts_acquisition_detention'].cout_total_entree }}</li>
        <li><strong>Coût de détention annuel réel :</strong> {{ data['9_couts_acquisition_detention'].cout_detention_annuel_reel }}</li>
        <li><strong>Financement (prix demandé) :</strong> {{ data['10_financement'].hypotheses_prix_demande }}</li>
        <li><strong>Financement (prix cible) :</strong> {{ data['10_financement'].hypotheses_prix_cible }}</li>
        <li><strong>Fonds propres :</strong> {{ data['10_financement'].composition_fonds_propres }}</li>
        <li><strong>Amortissement 2e rang :</strong> {{ data['10_financement'].modalites_amortissement_2e_rang }}</li>
    </ul>

    <h2>11. Fiscalité</h2>
    <ul>
        <li><strong>Impôt foncier :</strong> {{ data['11_fiscalite'].impact_impot_foncier }}</li>
        <li><strong>Suppression de la valeur locative (2029) :</strong> {{ data['11_fiscalite'].impact_suppression_valeur_locative_2029 }}</li>
    </ul>

    <h2>Annexes</h2>
    <table>
        <tr>
            <th colspan="3">Annexe A — Documents à réclamer</th>
        </tr>
        <tr>
            <td><strong>Document</strong></td>
            <td><strong>Permet de trancher</strong></td>
            <td><strong>Risque lié</strong></td>
        </tr>
        {% for doc in data['annexe_a_documents_a_reclamer'] %}
        <tr>
            <td>{{ doc.document }}</td>
            <td>{{ doc.permet_de_trancher }}</td>
            <td>N°{{ doc.numero_risque_lie }}</td>
        </tr>
        {% endfor %}
    </table>

    <p><strong>Annexe B — Points de visite spécifiques :</strong></p>
    <ul>
        {% for point in data['annexe_b_points_visite'] %}
        <li>☐ {{ point.point_a_verifier_sur_place }}</li>
        {% endfor %}
    </ul>

    <div class="avertissement">
        <strong>Avertissement :</strong> Cette note d'analyse pré-acquisition contient des estimations [E] et des données déclaratives non vérifiées [A]. Elle ne constitue ni un conseil en investissement, ni un avis juridique ou fiscal.
    </div>
</body>
</html>
"""

uploaded_file = st.file_uploader("📄 Déposez la plaquette ou le dossier immobilier (PDF)", type=["pdf"])

if uploaded_file:
    if st.button("Lancer l'analyse Due Diligence 🚀"):
        with st.spinner(f"Analyse approfondie en cours avec {modele_choisi}... (30 à 60 secondes)"):
            try:
                pdf_base64 = base64.b64encode(uploaded_file.read()).decode("utf-8")

                response = client.messages.create(
                model=modele_choisi,
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_base64
                            }
                        },
                        {
                            "type": "text",
                            "text": instructions_acheteur
                        }
                    ]
                }]
            )

                raw_text = response.content[0].text.strip()

                # Extraction propre du JSON même si l'IA ajoute ```json ... ```
                match = re.search(r"\{.*\}", raw_text, re.DOTALL)
                json_str = match.group(0) if match else raw_text
                donnees = json.loads(json_str)

                rendered_html = Template(HTML_TEMPLATE).render(data=donnees)
                pdf_bytes = HTML(string=rendered_html).write_pdf()

                st.success("✅ Analyse terminée ! Votre rapport PDF est prêt.")
                st.download_button(
                    label="📥 Télécharger la Note d'Analyse (PDF)",
                    data=pdf_bytes,
                    file_name="Note_Analyse_Acquisition.pdf",
                    mime="application/pdf"
                )

            except Exception as e:
                st.error(f"Une erreur s'est produite : {e}")
