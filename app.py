import streamlit as st
import base64
import json
import re
import anthropic
from jinja2 import Template
from weasyprint import HTML

# Configuration de la page
st.set_page_config(page_title="Analyse IA Immobilière", page_icon="🏢", layout="centered")

# --- CONSTANTES (Prompt & HTML) ---
SYSTEM_PROMPT = """# RÔLE ET EXPERTISE
Tu es un analyste immobilier senior, spécialisé dans la due diligence pré-acquisition en Suisse romande. L'utilisateur te fournit la documentation de vente d'un bien (plaquette, plans, CECB, etc.). Ta mission est de produire une note d'analyse d'acquisition exhaustive et critique.

# MÉTHODOLOGIE (À APPLIQUER STRICTEMENT)
1. Analyse documentaire : Lis toute la documentation. Les plans priment systématiquement sur le texte commercial.
2. Confrontation : 
   - Additionne les surfaces cotées et compare à la surface annoncée.
   - Distingue la surface habitable chauffée, surface PPE brute, surface pondérée, balcons/vérandas.
   - Relève tout écart entre le texte et les plans, et repère les éventuelles annexes non autorisées.
3. Données de marché et légales (Utilise tes connaissances internes sur la Suisse) :
   - Évalue le prix moyen/médian de la zone, le loyer de marché.
   - Applique le cadre légal (DACCE, LVLEne Vais/Vaud, etc.) et le taux d'imposition communal si connu.
4. Fiabilité des données (Indispensable) : 
   Précède chaque donnée chiffrée ou factuelle de son niveau de fiabilité :
   - [A] = Annoncé par le vendeur (non vérifié)
   - [E] = Estimation ou hypothèse de l'analyste
   - [V] = Vérifié, établi par une pièce au dossier.
   N'invente jamais une donnée absente : note-la comme "Manquante".

# HYPOTHÈSES DE CALCUL STANDARD À UTILISER
- Charge théorique bancaire : Taux calculatoire 5%, entretien 1%, amortissement 2e rang sur 15 ans jusqu'à 65% de la valeur, tenue à 33% du revenu brut.
- Frais d'acquisition : Vaud ~4,5% (mutation 3,3%, notaire/RF ~1,2%) ; Valais ~2,5% (mutation 1,5%, RF 0,2%, notaire 0,5-0,7%). Applicables aussi aux places de parc.
- Coût de détention réel : Taux effectif 1,5 à 2,0% (distinct du calculatoire).
- Financement : 10% de fonds propres durs minimum. 

# TON ET STYLE
Factuel, direct, sans emphase commerciale. Dis ce que tu ne sais pas. Chaque chiffre doit être traçable.

# FORMAT DE RÉPONSE EXIGÉ
Tu dois répondre UNIQUEMENT en format JSON valide. Aucun texte avant ou après. 
Utilise strictement la structure suivante, en remplissant tous les champs (utilise null ou "Non mentionné" si absent) :

{
  "1_synthese_et_verdict": {
    "verdict_conditionnel": "string (1 paragraphe)",
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
    "caracteristiques": [{"cle": "string", "valeur_et_fiabilite": "string (ex: [A] 120 m2)"}],
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
      "numero": "integer",
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
    {"document": "string", "permet_de_trancher": "string", "numero_risque_lie": "integer"}
  ],
  "annexe_b_points_visite": [
    {"point_a_verifier_sur_place": "string"}
  ]
}"""

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8">
    <style>
        @page { size: A4; margin: 15mm; }
        body { font-family: 'Georgia', serif; font-size: 11pt; color: #333; line-height: 1.4; }
        h1, h2, h3, th { font-family: 'Helvetica', sans-serif; color: #13294b; page-break-after: avoid; }
        h1 { border-bottom: 2px solid #1f5fa8; padding-bottom: 5px; font-size: 24px; }
        h2 { color: #1f5fa8; font-size: 16px; margin-top: 25px; border-bottom: 1px solid #e3ebf6; padding-bottom: 3px; }
        
        table { width: 100%; border-collapse: collapse; margin-bottom: 15px; page-break-inside: avoid; }
        th, td { padding: 8px; text-align: left; border: 1px solid #e3ebf6; font-size: 10pt; }
        th { background-color: #13294b; color: white; }
        tr:nth-child(even) { background-color: #f6f9fc; }
        tr:nth-child(odd) { background-color: #fff; }

        .encadre-verdict { border: 2px solid #1f5fa8; background-color: #f6f9fc; padding: 15px; border-radius: 5px; margin-bottom: 15px; }
        .encadre-alerte { border-left: 5px solid #e53e3e; background-color: #fff5f5; padding: 10px 15px; margin-bottom: 15px; }
        .encadre-etape { border-left: 5px solid #1f5fa8; background-color: #e3ebf6; padding: 10px 15px; margin-bottom: 15px; font-family: 'Helvetica', sans-serif; }
        
        /* Badges Risque */
        .badge-Faible { background-color: #3182ce; color: white; padding: 3px 6px; border-radius: 4px; font-size: 9pt; font-family: sans-serif; }
        .badge-Moyenne { background-color: #dd6b20; color: white; padding: 3px 6px; border-radius: 4px; font-size: 9pt; font-family: sans-serif; }
        .badge-Elevée { background-color: #e53e3e; color: white; padding: 3px 6px; border-radius: 4px; font-size: 9pt; font-family: sans-serif; }

        ul { margin-top: 5px; padding-left: 20px; }
        li { margin-bottom: 4px; }
        
        .avertissement { font-size: 8pt; color: #718096; text-align: justify; margin-top: 40px; border-top: 1px solid #e2e8f0; padding-top: 10px; }
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
        <strong>⚠️ Les alertes majeures :</strong>
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
        <li><strong>Arguments de négo :</strong> {{ data['8_strategie_offre'].arguments_negociation_par_poids | join(' | ') }}</li>
        <li><strong>Atouts vendeur :</strong> {{ data['8_strategie_offre'].atouts_vendeur | join(' | ') }}</li>
    </ul>

    <h2>9. Coûts & 10. Financement</h2>
    <ul>
        <li><strong>Coût total d'entrée (Frais inclus) :</strong> {{ data['9_couts_acquisition_detention'].cout_total_entree }}</li>
        <li><strong>Coût de détention annuel :</strong> {{ data['9_couts_acquisition_detention'].cout_detention_annuel_reel }}</li>
        <li><strong>Financement au prix cible :</strong> {{ data['10_financement'].hypotheses_prix_cible }}</li>
        <li><strong>Fonds propres :</strong> {{ data['10_financement'].composition_fonds_propres }}</li>
        <li><strong>Amortissement 2e rang :</strong> {{ data['10_financement'].modalites_amortissement_2e_rang }}</li>
    </ul>

    <h2>11. Fiscalité</h2>
    <ul>
        <li><strong>Impôt foncier :</strong> {{ data['11_fiscalite'].impact_impot_foncier }}</li>
        <li><strong>Fin de la valeur locative (2029) :</strong> {{ data['11_fiscalite'].impact_suppression_valeur_locative_2029 }}</li>
    </ul>

    <h2>Annexes</h2>
    <table>
        <tr>
            <th colspan="3">A - Documents à réclamer</th>
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

    <ul>
        <strong>B - Checklist de visite sur place :</strong>
        {% for point in data['annexe_b_points_visite'] %}
        <li>☐ {{ point.point_a_verifier_sur_place }}</li>
        {% endfor %}
    </ul>

    <div class="avertissement">
        <strong>Avertissement :</strong> Cette note d'analyse a été générée automatiquement. Elle contient des estimations (marquées [E]) et des données non vérifiées (marquées [A]). Ce document ne constitue ni un conseil en investissement, ni une expertise juridique ou fiscale.
    </div>
</body>
</html>
"""

# --- INTERFACE UTILISATEUR ---
st.title("🏢 Analyseur de Plaquette Immobilière (IA)")
st.write("Uploadez une plaquette commerciale (PDF) pour obtenir un audit automatique (Red Flags, Prix, Agencement).")

# Streamlit va chercher la clé de manière invisible dans son coffre-fort
api_key = st.secrets["ANTHROPIC_API_KEY"]

# Zone d'upload
uploaded_file = st.file_uploader("Chargez le PDF de la plaquette", type=["pdf"])

if uploaded_file:
    if st.button("Lancer l'analyse 🚀"):
        # st.spinner affiche une animation de chargement pendant l'exécution du bloc "with"
        with st.spinner("Analyse en cours par Claude 3.5 Sonnet (cela peut prendre 15 à 30 secondes)..."):
            try:
                # 1. Préparation du PDF
                pdf_bytes = uploaded_file.read()
                pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
                
                # 2. Appel à l'API Claude
                client = anthropic.Anthropic(api_key=api_key)
                response = client.messages.create(
                   model="claude-3-haiku-20240307",
                    max_tokens=4096,
                    extra_body={"temperature": 0.1},  # <-- La nouvelle méthode stricte est ici
                    system=SYSTEM_PROMPT,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_base64}},
                            {"type": "text", "text": "Analyse ce document et renvoie uniquement le JSON valide."}
                        ]
                    }]
                )
                
                # 3. Extraction du JSON
                raw_text = response.content[0].text.strip()
                clean_json = re.search(r"\{.*\}", raw_text, re.DOTALL).group(0)
                donnees = json.loads(clean_json)
                
                # 4. Génération du PDF avec Jinja2 et WeasyPrint
                rendered_html = Template(HTML_TEMPLATE).render(data=donnees)
                pdf_output = HTML(string=rendered_html).write_pdf()
                
                st.success("✅ Analyse terminée avec succès !")
                
                # 5. Bouton de téléchargement natif de Streamlit
                st.download_button(
                    label="📥 Télécharger le compte-rendu (PDF)",
                    data=pdf_output,
                    file_name=f"Analyse_{uploaded_file.name}",
                    mime="application/pdf"
                )
                
            except Exception as e:
                st.error(f"Une erreur s'est produite : {str(e)}")
elif uploaded_file and not api_key:
    st.warning("👈 Veuillez entrer votre clé API Anthropic dans la barre latérale pour continuer.")
