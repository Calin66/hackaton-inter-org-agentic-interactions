
# Synthetic tariff table used by the agent. Extend as needed.
SYNTHETIC_TARIFF = {
    # Emergency & consults
    "ER visit low complexity": 250,
    "ER visit moderate complexity": 650,
    "ER visit high complexity": 1200,
    "Initial consult": 180,
    "Specialist consult": 320,
    # Imaging
    "X-ray forearm": 300,
    "X-ray chest": 220,
    "CT head without contrast": 950,
    "CT abdomen with contrast": 1400,
    "MRI knee without contrast": 1700,
    "MRI brain with/without contrast": 2400,
    # Labs
    "Complete blood count (CBC)": 60,
    "Comprehensive metabolic panel": 85,
    "Lipid panel": 90,
    "HbA1c": 55,
    # Procedures / surgery
    "Forearm fracture reduction": 2100,
    "Laceration repair simple": 400,
    "Laceration repair complex": 1150,
    "Arthroscopy knee": 5200,
    # Therapy
    "Physical therapy session": 130,
    "Occupational therapy session": 140,
}
