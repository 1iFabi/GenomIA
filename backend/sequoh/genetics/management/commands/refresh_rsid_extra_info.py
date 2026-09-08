
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Optional

from django.core.management.base import BaseCommand

from genetics.models import RsidExtraInfo


DISCLAIMER = "Esto es informativo y no constituye diagnostico medico."
FILLER_SENTENCES = [
    "Este resultado refleja una tendencia biologica y no determina por si solo el resultado clinico.",
    "Factores de estilo de vida, ambiente y otros genes tambien influyen en este rasgo.",
]

LEVEL_MAP = [
    ("muy elevado", ["muy elevado", "muy alta", "muy alto", "ultra rapido"]),
    ("elevado", ["elevado", "elevada", "alto", "alta", "mayor"]),
    ("intermedio", ["intermedio", "intermedia"]),
    ("reducido", ["reducido", "reducida", "lento", "lenta", "pobre", "deficiencia", "menor"]),
    ("bajo", ["bajo", "baja"]),
    ("normal", ["normal", "estandar", "extenso"]),
    ("optimo", ["optimo", "optima"]),
    ("severo", ["severo", "severa"]),
    ("moderado", ["moderado", "moderada"]),
]


CONDITION_INFO = {
    "alzheimer": [
        "El Alzheimer es una enfermedad neurodegenerativa progresiva que afecta la memoria y otras funciones cognitivas.",
        "Se asocia con acumulacion de proteinas anormales, perdida de neuronas y atrofia de regiones cerebrales, con deterioro del juicio y la conducta.",
        "Su evolucion suele ser lenta y puede afectar la autonomia diaria.",
    ],
    "parkinson": [
        "La enfermedad de Parkinson es un trastorno neurodegenerativo que afecta principalmente el control del movimiento.",
        "Se caracteriza por temblor en reposo, rigidez, lentitud motora y alteraciones posturales, con sintomas no motores.",
        "La evolucion es gradual y el impacto funcional varia entre personas.",
    ],
    "crohn": [
        "La enfermedad de Crohn es una enfermedad inflamatoria intestinal cronica que puede afectar cualquier tramo del tubo digestivo.",
        "Provoca dolor abdominal, diarrea, fatiga y perdida de peso, con periodos de brote y remision.",
        "Su origen es multifactorial, con componentes inmunes y ambientales.",
    ],
    "colitis ulcerosa": [
        "La colitis ulcerosa es una enfermedad inflamatoria cronica que afecta el colon y el recto.",
        "Produce inflamacion continua de la mucosa, diarrea con sangre y urgencia intestinal.",
        "Puede presentar brotes y requerir seguimiento a largo plazo.",
    ],
    "enfermedad celiaca": [
        "La enfermedad celiaca es una reaccion autoinmune al gluten que dana el intestino delgado.",
        "Puede causar malabsorcion, molestias digestivas y sintomas extraintestinales.",
        "Mejora con dieta sin gluten y depende de predisposicion genetica.",
    ],
    "esclerosis multiple": [
        "La esclerosis multiple es una enfermedad autoinmune del sistema nervioso central que afecta la mielina.",
        "Genera sintomas neurologicos variables como alteraciones visuales, debilidad o problemas de equilibrio.",
        "El curso puede alternar brotes y remisiones con evolucion diversa.",
    ],
    "esquizofrenia": [
        "La esquizofrenia es un trastorno mental cronico con alteraciones del pensamiento, la percepcion y la conducta.",
        "Puede incluir delirios, alucinaciones y deterioro del funcionamiento social.",
        "Su origen es multifactorial y requiere evaluacion clinica integral.",
    ],
    "trastorno bipolar": [
        "El trastorno bipolar es una condicion del estado de animo con episodios de mania o hipomania y depresion.",
        "Estos cambios pueden afectar energia, sueno, impulsividad y funcionamiento diario.",
        "El curso es variable y suele requerir seguimiento clinico.",
    ],
    "depresion": [
        "La depresion es un trastorno del estado de animo con tristeza persistente, perdida de interes y baja energia.",
        "Puede acompanarse de cambios en el sueno, el apetito y la concentracion.",
        "Su origen incluye factores biologicos, psicologicos y sociales.",
    ],
    "ansiedad": [
        "Los trastornos de ansiedad implican preocupacion excesiva y activacion fisiologica sostenida.",
        "Se manifiestan con tension, inquietud, palpitaciones y dificultades de concentracion o sueno.",
        "Se relacionan con predisposicion genetica y estres ambiental.",
    ],
    "trastornos del animo": [
        "Los trastornos del animo abarcan condiciones donde el estado emocional se altera de forma persistente.",
        "Esto puede incluir tristeza intensa, irritabilidad o cambios marcados de energia y motivacion.",
        "Su expresion depende de factores biologicos, psicologicos y contextuales.",
    ],
    "tdah": [
        "El TDAH es un trastorno del neurodesarrollo con inatencion, hiperactividad e impulsividad.",
        "Puede afectar rendimiento escolar, laboral y relaciones sociales.",
        "Su expresion es variable y suele mejorar con apoyo y manejo adecuado.",
    ],
    "migrana": [
        "La migrana es un trastorno neurologico con cefaleas recurrentes, a veces con aura.",
        "Se asocia con nauseas, sensibilidad a la luz o al sonido y limitacion funcional.",
        "Su causa es compleja y puede tener desencadenantes ambientales.",
    ],
    "glaucoma": [
        "El glaucoma es una enfermedad ocular que dana el nervio optico, a menudo por aumento de presion intraocular.",
        "Puede provocar perdida progresiva del campo visual si no se detecta a tiempo.",
        "El control temprano ayuda a preservar la vision.",
    ],
    "degeneracion macular": [
        "La degeneracion macular relacionada con la edad afecta la macula, responsable de la vision central.",
        "Produce vision borrosa y dificultad para leer o reconocer rostros.",
        "Su riesgo aumenta con la edad y otros factores.",
    ],
    "cancer colorrectal": [
        "El cancer colorrectal se origina en el colon o el recto por crecimiento descontrolado de celulas.",
        "Puede manifestarse con cambios en el habito intestinal, sangrado o anemia.",
        "La deteccion precoz mejora el pronostico.",
    ],
    "cancer de mama": [
        "El cancer de mama es el crecimiento maligno de celulas del tejido mamario.",
        "Puede presentarse con un bulto o cambios en la piel, aunque al inicio puede ser asintomatico.",
        "El riesgo depende de factores geneticos, hormonales y ambientales.",
    ],
    "cancer de ovario": [
        "El cancer de ovario es una neoplasia que se desarrolla en los ovarios o tejidos cercanos.",
        "Puede causar sintomas inespecificos como distension abdominal o dolor pelvico.",
        "El diagnostico temprano es dificil, por lo que la vigilancia es relevante.",
    ],
    "cancer de prostata": [
        "El cancer de prostata es un crecimiento maligno en la glandula prostatica.",
        "Puede causar sintomas urinarios, aunque al inicio suele ser silencioso.",
        "Su evolucion varia segun el estadio y la agresividad.",
    ],
    "cancer de pulmon": [
        "El cancer de pulmon se origina en el tejido pulmonar y puede afectar la respiracion.",
        "Se asocia con tos persistente, disnea o perdida de peso.",
        "El tabaquismo es un factor de riesgo importante.",
    ],
    "cancer de vejiga": [
        "El cancer de vejiga afecta el revestimiento interno de la vejiga urinaria.",
        "Puede manifestarse con sangre en la orina o molestias al orinar.",
        "Factores como el tabaquismo y exposiciones quimicas aumentan el riesgo.",
    ],
    "cancer gastrico": [
        "El cancer gastrico se desarrolla en el estomago y puede causar dolor, perdida de apetito o anemia.",
        "En fases tempranas los sintomas pueden ser leves o ausentes.",
        "La infeccion por H. pylori y otros factores influyen en el riesgo.",
    ],
    "melanoma": [
        "El melanoma es un cancer de piel originado en melanocitos, las celulas que producen melanina.",
        "Puede aparecer como un lunar nuevo o un cambio en un lunar existente.",
        "La exposicion solar y la predisposicion genetica influyen en el riesgo.",
    ],
    "psoriasis": [
        "La psoriasis es una enfermedad inflamatoria cronica de la piel.",
        "Se caracteriza por placas rojas con descamacion y puede asociarse a dolor articular.",
        "Su curso es variable y puede desencadenarse por estres o infecciones.",
    ],
    "vitiligo": [
        "El vitiligo es una condicion en la que se pierden melanocitos, generando manchas blancas en la piel.",
        "Su distribucion puede ser localizada o extensa y afecta la pigmentacion.",
        "El origen es complejo y puede incluir factores autoinmunes.",
    ],
    "artritis reumatoide": [
        "La artritis reumatoide es una enfermedad autoinmune que inflama articulaciones.",
        "Produce dolor, rigidez matinal e hinchazon, y a largo plazo puede causar deformidades.",
        "El control temprano ayuda a preservar la funcion articular.",
    ],
    "enfermedad coronaria": [
        "La enfermedad coronaria implica estrechamiento de las arterias que irrigan el corazon.",
        "Se relaciona con aterosclerosis y puede causar angina o infarto.",
        "Factores como colesterol, presion y tabaquismo influyen en el riesgo.",
    ],
    "hipertension": [
        "La hipertension es la elevacion persistente de la presion arterial.",
        "Aumenta el riesgo de infarto, accidente cerebrovascular y dano renal.",
        "Su control incluye cambios de estilo de vida y tratamiento medico.",
    ],
    "diabetes tipo 2": [
        "La diabetes tipo 2 es una alteracion metabolica con resistencia a la insulina y elevacion de glucosa.",
        "Puede causar sed, fatiga y a largo plazo danar vasos, rinones y vision.",
        "El manejo incluye dieta, actividad fisica y seguimiento medico.",
    ],
    "diabetes gestacional": [
        "La diabetes gestacional es elevacion de glucosa detectada durante el embarazo.",
        "Puede afectar el crecimiento del bebe y aumentar complicaciones obstetricas.",
        "Suele mejorar tras el parto, pero eleva riesgo futuro de diabetes.",
    ],
    "obesidad": [
        "La obesidad es un exceso de grasa corporal que afecta el metabolismo.",
        "Se relaciona con mayor riesgo de diabetes, hipertension y enfermedad cardiovascular.",
        "Su desarrollo depende de dieta, actividad, entorno y genetica.",
    ],
    "obesidad infantil": [
        "La obesidad infantil es exceso de grasa corporal en la infancia.",
        "Puede afectar el desarrollo, la salud metabolica y el riesgo cardiovascular futuro.",
        "Factores geneticos, alimentacion y actividad influyen en su aparicion.",
    ],
    "colesterol elevado": [
        "El colesterol elevado, especialmente LDL, favorece la formacion de placas en arterias.",
        "Esto incrementa el riesgo de enfermedad cardiovascular.",
        "El nivel de colesterol depende de dieta, actividad y genetica.",
    ],
    "fractura osea": [
        "Las fracturas oseas ocurren cuando el hueso se rompe por trauma o fragilidad.",
        "El riesgo aumenta con baja densidad osea, edad y caidas.",
        "La prevencion incluye fortalecimiento oseo y reducir riesgos de caida.",
    ],
    "osteoporosis": [
        "La osteoporosis es una disminucion de la densidad y calidad del hueso.",
        "Esto aumenta la fragilidad y el riesgo de fracturas.",
        "Factores hormonales, nutricionales y geneticos influyen en su desarrollo.",
    ],
    "hemocromatosis": [
        "La hemocromatosis es un trastorno de sobrecarga de hierro por exceso de absorcion.",
        "El hierro se deposita en organos como higado, pancreas y articulaciones, causando dano progresivo.",
        "El tratamiento temprano puede prevenir complicaciones.",
    ],
    "hepatitis b cronica": [
        "La hepatitis B cronica es una infeccion persistente del higado por el virus de la hepatitis B.",
        "Puede causar inflamacion cronica, cirrosis y aumentar riesgo de cancer hepatocelular.",
        "Su evolucion es variable y requiere seguimiento.",
    ],
    "trombosis venosa": [
        "La trombosis venosa es la formacion de coagulos en venas profundas.",
        "Puede causar dolor e hinchazon y existe riesgo de embolia pulmonar.",
        "Factores geneticos y ambientales influyen en la coagulacion.",
    ],
    "factor v leiden": [
        "El factor V Leiden es una mutacion que aumenta la tendencia a formar coagulos.",
        "Eleva el riesgo de trombosis venosa, especialmente con otros factores de riesgo.",
        "Su impacto depende del estado genetico y del contexto clinico.",
    ],
    "protrombina g20210a": [
        "La mutacion G20210A en la protrombina aumenta sus niveles en sangre.",
        "Esto favorece la coagulacion y eleva el riesgo de trombosis venosa.",
        "El riesgo depende de otros factores y del estado genetico.",
    ],
    "atrofia cerebral": [
        "La atrofia cerebral es la reduccion del volumen del cerebro.",
        "Se asocia con envejecimiento y procesos neurodegenerativos, con impacto en memoria y funciones ejecutivas.",
        "La progresion puede variar segun la causa.",
    ],
    "enfermedades autoinmunes": [
        "Las enfermedades autoinmunes ocurren cuando el sistema inmune ataca tejidos propios.",
        "Esto puede afectar distintos organos y causar inflamacion cronica.",
        "Su origen es multifactorial, con componentes geneticos y ambientales.",
    ],
    "adicciones": [
        "Las adicciones son trastornos de conducta con consumo compulsivo y perdida de control.",
        "Se asocian a cambios en circuitos de recompensa del cerebro y afectan la vida social y laboral.",
        "Factores geneticos, ambientales y psicologicos influyen.",
    ],
    "adiccion al tabaco": [
        "La adiccion al tabaco es un trastorno de dependencia relacionado con la nicotina.",
        "La nicotina genera refuerzo, tolerancia y sintomas de abstinencia que dificultan dejar de fumar.",
        "La predisposicion genetica influye en la intensidad de la dependencia.",
    ],
    "dependencia a alcohol": [
        "La dependencia al alcohol implica consumo problematico, tolerancia y sintomas de abstinencia.",
        "Puede afectar higado, sistema nervioso y relaciones personales.",
        "El riesgo depende de factores geneticos, sociales y de consumo.",
    ],
    "asma": [
        "El asma es una enfermedad inflamatoria cronica de las vias respiratorias.",
        "Se caracteriza por episodios de broncoespasmo, sibilancias y dificultad respiratoria.",
        "Factores alergicos y ambientales influyen en su aparicion.",
    ],
    "asma infantil": [
        "El asma infantil es inflamacion cronica de las vias respiratorias con inicio en la infancia.",
        "Provoca episodios de tos, sibilancias y dificultad respiratoria, a menudo desencadenados por alergenos.",
        "El control temprano ayuda a reducir crisis y limitar sintomas.",
    ],
    "lupus eritematoso": [
        "El lupus eritematoso es una enfermedad autoinmune sistemica.",
        "Puede afectar piel, articulaciones, rinones y otros organos, con brotes de inflamacion.",
        "Su manifestacion es variable y requiere seguimiento clinico.",
    ],
}

CONDITION_ALIASES = {
    "amd": "degeneracion macular",
    "degeneracion macular": "degeneracion macular",
    "lupus eritematoso sistemico": "lupus eritematoso",
    "hemocromatosis hereditaria": "hemocromatosis",
    "dependencia nicotinica": "adiccion al tabaco",
    "nicotina": "adiccion al tabaco",
    "alcohol": "dependencia a alcohol",
    "alcoholismo": "dependencia a alcohol",
}

for alias, target in CONDITION_ALIASES.items():
    CONDITION_INFO[alias] = CONDITION_INFO[target]

CONDITION_KEYS = sorted(CONDITION_INFO.keys(), key=len, reverse=True)


BIOMARKER_INFO = {
    "homocisteina": [
        "La homocisteina es un aminoacido relacionado con el metabolismo del folato y la vitamina B12.",
        "Niveles elevados se han asociado con mayor riesgo cardiovascular y efectos vasculares.",
    ],
    "proteina c reactiva": [
        "La proteina C reactiva es un marcador de inflamacion sistemica producido por el higado.",
        "Valores altos pueden reflejar inflamacion aguda o cronica en el organismo.",
    ],
    "interleucina 10": [
        "La interleucina 10 es una citocina antiinflamatoria que regula la respuesta inmune.",
        "Ayuda a limitar la inflamacion y a mantener el equilibrio inmunologico.",
    ],
    "interferon gamma": [
        "El interferon gamma participa en la defensa frente a infecciones y en la activacion de celulas inmunes.",
        "Su nivel puede reflejar intensidad de la respuesta inmune celular.",
    ],
    "tnf alfa": [
        "El TNF alfa es una citocina proinflamatoria involucrada en inflamacion y respuesta al estres.",
        "Niveles altos pueden asociarse a procesos inflamatorios sostenidos.",
    ],
    "tgf beta1": [
        "El TGF beta1 regula crecimiento celular, cicatrizacion e inmunidad.",
        "Su variacion puede influir en reparacion de tejidos y control inflamatorio.",
    ],
    "calcitonina": [
        "La calcitonina es una hormona tiroidea que participa en el control del calcio y el metabolismo oseo.",
        "Sus niveles se relacionan con balance mineral y actividad de hueso.",
    ],
    "bdnf": [
        "El BDNF es una proteina que apoya la supervivencia neuronal y la plasticidad sinaptica.",
        "Se asocia con aprendizaje, memoria y regulacion del animo.",
    ],
    "vitamina d": [
        "La vitamina D regula absorcion de calcio y salud osea, y tambien modula funciones inmunes.",
        "Niveles adecuados favorecen el equilibrio mineral y la funcion muscular.",
    ],
    "hierro": [
        "El hierro es esencial para el transporte de oxigeno y la produccion de energia.",
        "El exceso puede llevar a sobrecarga y dano en organos.",
    ],
    "hormona de crecimiento": [
        "La hormona de crecimiento regula el crecimiento corporal, la masa muscular y el metabolismo.",
        "Su variacion puede influir en composicion corporal y energia.",
    ],
    "metionina": [
        "La metionina es un aminoacido clave en procesos de metilacion y sintesis de proteinas.",
        "Su metabolismo se relaciona con folato, vitamina B12 y homocisteina.",
    ],
    "interleucina 6": [
        "La interleucina 6 es una citocina proinflamatoria que participa en la respuesta inmune.",
        "Niveles altos se asocian con inflamacion sistemica y cambios metabolicos.",
    ],
}

BIOMARKER_PATTERNS = {
    "homocisteina": ["homocisteina"],
    "proteina c reactiva": ["proteina c reactiva", "pcr", "crp"],
    "interleucina 10": ["interleucina 10", "il 10", "il-10"],
    "interferon gamma": ["interferon gamma", "ifng"],
    "tnf alfa": ["tnf alfa", "tnf"],
    "tgf beta1": ["tgf beta1", "tgf beta"],
    "calcitonina": ["calcitonina"],
    "bdnf": ["bdnf"],
    "vitamina d": ["vitamina d"],
    "hierro": ["hierro"],
    "hormona de crecimiento": ["hormona de crecimiento", "gh1"],
    "metionina": ["metionina"],
    "interleucina 6": ["interleucina 6", "il6"],
}

BIOMETRIC_INFO = {
    "densidad osea": [
        "La densidad osea refleja la cantidad de mineral en los huesos y su resistencia mecanica.",
        "Valores bajos aumentan riesgo de fracturas y osteoporosis, mientras que valores altos indican mayor fortaleza.",
    ],
    "hdl colesterol": [
        "El HDL transporta colesterol desde tejidos al higado para su eliminacion.",
        "Niveles altos suelen asociarse a menor riesgo cardiovascular, mientras que niveles bajos elevan el riesgo.",
    ],
    "folato": [
        "El folato participa en la sintesis de ADN y en rutas de metilacion.",
        "Un metabolismo reducido puede elevar homocisteina y afectar la salud vascular.",
    ],
    "acidos grasos": [
        "El metabolismo de acidos grasos influye en energia, inflamacion y perfiles lipidicos.",
        "Variaciones geneticas pueden modificar el uso de grasas como fuente energetica.",
    ],
    "insulina": [
        "La sensibilidad a insulina determina como las celulas responden a esta hormona y regulan la glucosa.",
        "Una sensibilidad reducida se asocia con resistencia a insulina y riesgo metabolico.",
    ],
    "estrogenos": [
        "La sensibilidad a estrogenos influye en funciones reproductivas, salud osea y metabolismo.",
        "Cambios en la senalizacion estrogenica pueden modificar sintomas y riesgo de ciertas condiciones.",
    ],
    "cardiovascular": [
        "La proteccion cardiovascular se relaciona con menor tendencia a aterosclerosis y eventos cardiacos.",
        "Factores geneticos pueden modular metabolismo de lipidos e inflamacion vascular.",
    ],
    "altura": [
        "La adaptacion metabolica a altura se relaciona con uso eficiente de oxigeno y energia.",
        "Puede influir en rendimiento fisico en ambientes de baja presion de oxigeno.",
    ],
}

BIOMETRIC_PATTERNS = {
    "densidad osea": ["densidad osea"],
    "hdl colesterol": ["hdl colesterol"],
    "folato": ["folato"],
    "acidos grasos": ["acidos grasos"],
    "insulina": ["insulina"],
    "estrogenos": ["estrogenos"],
    "cardiovascular": ["cardiovascular", "proteccion cardiovascular", "factor protector cardiovascular"],
    "altura": ["altura"],
}

TRAIT_INFO = {
    "pigmentacion": [
        "La pigmentacion de piel, ojos y cabello depende de la cantidad y tipo de melanina.",
        "Variaciones geneticas modifican la tonalidad, la respuesta al sol y la presencia de pecas.",
        "Este rasgo describe una tendencia a pigmentacion mas clara u oscura.",
    ],
    "cerumen": [
        "El tipo de cerumen depende de la secrecion de glandulas en el conducto auditivo.",
        "Algunas variantes se asocian con cerumen seco o humedo y con diferencias en olor corporal.",
        "Este rasgo no implica enfermedad, pero describe una caracteristica fisica heredable.",
    ],
    "sabor amargo": [
        "La percepcion del sabor amargo depende de receptores gustativos en la lengua.",
        "Mayor sensibilidad puede influir en preferencias alimentarias y consumo de ciertos vegetales o bebidas.",
        "Este rasgo es habitual en la poblacion y varia entre personas.",
    ],
    "sueno": [
        "La calidad del sueno se relaciona con ciclos circadianos y regulacion de neurotransmisores.",
        "Variantes geneticas pueden influir en facilidad para conciliar o mantener el sueno.",
        "El resultado describe una tendencia en el descanso, no un diagnostico.",
    ],
    "dopamina": [
        "La dopamina es un neurotransmisor clave en motivacion, recompensa, control motor y atencion.",
        "Cambios en receptores o enzimas pueden modificar su disponibilidad y afectar impulsividad o tono emocional.",
        "Este rasgo describe una tendencia en la funcion dopaminergica.",
    ],
    "anandamida": [
        "La anandamida es un endocannabinoide que modula animo, estres, apetito y percepcion del dolor.",
        "Sus niveles pueden variar por enzimas que la sintetizan o degradan.",
        "El resultado sugiere una tendencia en esta via de regulacion.",
    ],
    "dolor": [
        "El umbral de dolor describe cuan sensible es una persona a estimulos dolorosos.",
        "Variaciones en receptores opioides pueden modificar la respuesta al dolor y al alivio.",
        "Este rasgo es una tendencia y puede variar con contexto y experiencia.",
    ],
    "rendimiento": [
        "El rendimiento atletico se relaciona con el tipo de fibras musculares y el metabolismo energetico.",
        "Algunas variantes favorecen potencia y explosividad, otras resistencia y eficiencia.",
        "El resultado describe una predisposicion general, no el rendimiento real.",
    ],
    "lactosa": [
        "La tolerancia a lactosa depende de la persistencia de la enzima lactasa en la edad adulta.",
        "Una produccion baja puede causar molestias digestivas tras consumir lacteos.",
        "La expresion del rasgo tambien depende de la cantidad y frecuencia de consumo.",
    ],
    "abo": [
        "El estado secretor ABO describe si los antigenos del grupo sanguineo se expresan en secreciones.",
        "Esto puede influir en microbiota y susceptibilidad a ciertas infecciones.",
        "Es una caracteristica genetica estable y no implica enfermedad por si sola.",
    ],
    "social": [
        "Los rasgos de sociabilidad y empatia se relacionan con la comunicacion interpersonal.",
        "Genes asociados a la oxitocina pueden influir en sensibilidad social y vinculacion.",
        "El resultado indica una tendencia, modulada por experiencia y entorno.",
    ],
    "cognitivo": [
        "La funcion cognitiva incluye memoria, atencion y velocidad de procesamiento.",
        "Algunas variantes geneticas se asocian con diferencias sutiles en rendimiento o envejecimiento cognitivo.",
        "Este rasgo no determina capacidad individual y depende de multiples factores.",
    ],
    "alcohol_metabolism": [
        "El metabolismo del alcohol depende de enzimas que convierten etanol en acetaldehido y luego en acetato.",
        "Variaciones geneticas pueden modificar la velocidad de metabolizacion y la sensibilidad al alcohol.",
        "Esto puede influir en reacciones fisicas y en tolerancia percibida.",
    ],
    "generic": [
        "Este rasgo describe una caracteristica biologica o conductual influida por multiples genes.",
        "Las variaciones geneticas pueden modificar la expresion del rasgo en distintas intensidades.",
        "El resultado muestra una tendencia general dentro de la poblacion.",
    ],
}

TRAIT_PATTERNS = {
    "pigmentacion": ["pigmentacion", "piel", "ojos", "cabello", "pecas"],
    "cerumen": ["cerumen"],
    "sabor amargo": ["sabor amargo"],
    "sueno": ["sueno"],
    "dopamina": ["dopamina"],
    "anandamida": ["anandamida"],
    "dolor": ["dolor"],
    "rendimiento": ["rendimiento", "potencia muscular", "resistencia deportiva"],
    "lactosa": ["lactosa", "lactasa"],
    "abo": ["antigenos abo", "secretor", "secrecion de antigenos"],
    "social": ["sociabilidad", "empatia", "comportamiento social"],
    "cognitivo": ["cognitivo", "cognitiva", "memoria", "declive"],
    "alcohol_metabolism": ["alcohol", "etanol", "adh1b", "aldh2"],
}

PHARMA_GENES = {
    "CYP1A2",
    "CYP1A1",
    "CYP2B6",
    "CYP2C9",
    "CYP2C19",
    "CYP2D6",
    "CYP3A5",
    "DPYD",
    "NQO1",
    "GSTP1",
    "VKORC1",
    "ABCG2",
    "ADRB1",
    "ADRB2",
    "OPRM1",
    "IFNL3",
    "IL28B",
    "HTR2A",
    "TYMS",
}

PHARMA_KEYWORDS = [
    "warfarina",
    "clopidogrel",
    "tacrolimus",
    "codeina",
    "omeprazol",
    "efavirenz",
    "fluorouracilo",
    "metotrexato",
    "salbutamol",
    "interferon",
    "antivirales",
    "beta 2",
    "betabloqueadores",
    "atenolol",
    "estatinas",
    "antidepresivos",
    "antipsicoticos",
    "anticoagulantes",
    "broncodilatadores",
    "opioides",
    "cafeina",
    "carcinogenos",
]

DRUG_LABELS = {
    "warfarina": "warfarina",
    "clopidogrel": "clopidogrel",
    "tacrolimus": "tacrolimus",
    "codeina": "codeina",
    "omeprazol": "omeprazol",
    "efavirenz": "efavirenz",
    "fluorouracilo": "fluorouracilo",
    "metotrexato": "metotrexato",
    "salbutamol": "salbutamol",
    "interferon": "interferon",
    "antivirales": "antivirales",
    "beta 2": "agonistas beta-2",
    "betabloqueadores": "betabloqueadores",
    "atenolol": "atenolol",
    "estatinas": "estatinas",
    "antidepresivos": "antidepresivos",
    "antipsicoticos": "antipsicoticos",
    "anticoagulantes": "anticoagulantes",
    "broncodilatadores": "broncodilatadores",
    "opioides": "opioides",
    "cafeina": "cafeina",
    "carcinogenos": "carcinogenos",
}


def normalize(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def split_gene(phenotype_name: str) -> tuple[str, Optional[str]]:
    if not phenotype_name:
        return "", None
    match = re.search(r"\(([^)]+)\)\s*$", phenotype_name)
    if not match:
        return phenotype_name.strip(), None
    return phenotype_name[: match.start()].strip(), match.group(1).strip()


def detect_condition_key(norm: str) -> Optional[str]:
    for key in CONDITION_KEYS:
        if key in norm:
            return key
    return None


def detect_level(norm: str) -> Optional[str]:
    for canonical, variants in LEVEL_MAP:
        for variant in variants:
            if variant in norm:
                return canonical
    return None


def detect_pattern_key(norm: str, patterns: dict[str, Iterable[str]]) -> Optional[str]:
    for key, variants in patterns.items():
        for variant in variants:
            if variant in norm:
                return key
    return None


def pharma_level_effect(level: Optional[str]) -> str:
    if level in {"reducido", "bajo", "severo"}:
        return "una menor capacidad de procesamiento y mayor exposicion."
    if level in {"elevado", "muy elevado", "optimo"}:
        return "una mayor capacidad de procesamiento y posible menor exposicion."
    if level == "intermedio":
        return "un comportamiento intermedio entre rapido y lento."
    if level == "normal":
        return "una respuesta similar a la poblacion general."
    return "una variacion potencial en la respuesta."


def level_sentence(norm: str) -> Optional[str]:
    level = detect_level(norm)
    if not level:
        return None
    if "proteccion" in norm:
        return f"El resultado indica una proteccion {level} frente a este resultado."
    if "susceptibilidad" in norm:
        return f"El resultado sugiere una susceptibilidad {level} comparada con la poblacion general."
    if "riesgo" in norm or "mayor" in norm:
        return f"El resultado sugiere un riesgo {level} para esta condicion en comparacion con la poblacion general."
    if "actividad" in norm or "metabolismo" in norm or "metabolizador" in norm:
        return f"El nivel observado es {level}, lo que puede modificar la velocidad de procesamiento."
    if "niveles" in norm or "produccion" in norm:
        return f"El nivel estimado es {level}, lo que refleja una tendencia biologica en ese rango."
    return f"El nivel observado es {level} en este rasgo."


def finalize(sentences: Iterable[str]) -> str:
    parts = [s.strip() for s in sentences if s and s.strip()]
    if not parts:
        return DISCLAIMER
    if parts[-1] != DISCLAIMER:
        parts.append(DISCLAIMER)
    text = " ".join(parts)
    while len(text.split()) < 70:
        for filler in FILLER_SENTENCES:
            parts.insert(-1, filler)
            text = " ".join(parts)
            if len(text.split()) >= 70:
                break
        else:
            break
    while len(text.split()) > 120 and len(parts) > 2:
        parts.pop(-2)
        text = " ".join(parts)
    return text


def build_condition_description(norm: str, gene: Optional[str]) -> str:
    key = detect_condition_key(norm)
    sentences = list(CONDITION_INFO.get(key, []))
    level_info = level_sentence(norm)
    if level_info:
        sentences.append(level_info)
    if gene:
        sentences.append(f"El gen {gene} participa en rutas biologicas relacionadas con este resultado.")
    return finalize(sentences)


def build_pharma_description(norm: str, gene: Optional[str]) -> str:
    sentences: list[str] = []
    drug_key = detect_pattern_key(norm, {k: [k] for k in DRUG_LABELS.keys()})
    drug_label = DRUG_LABELS.get(drug_key) if drug_key else None
    if drug_label:
        sentences.append(
            f"Este resultado se relaciona con la respuesta o el metabolismo de {drug_label}, un farmaco usado en distintos contextos clinicos."
        )
    else:
        sentences.append("Este resultado describe la forma en que el organismo procesa ciertos farmacos.")
    sentences.append(
        "Las variantes geneticas pueden modificar la velocidad de metabolizacion o la sensibilidad, afectando concentraciones y efectos."
    )
    level = detect_level(norm)
    sentences.append(f"El nivel observado sugiere {pharma_level_effect(level)}")
    if gene:
        sentences.append(f"El gen {gene} participa en esta via metabolica o en el receptor implicado.")
    return finalize(sentences)


def build_biomarker_description(norm: str, gene: Optional[str]) -> str:
    key = detect_pattern_key(norm, BIOMARKER_PATTERNS)
    sentences = list(BIOMARKER_INFO.get(key, []))
    if not sentences:
        sentences.append("Este resultado se refiere a niveles o produccion de un biomarcador biologico.")
        sentences.append("Los biomarcadores reflejan procesos inflamatorios, metabolicos o de crecimiento.")
    level_info = level_sentence(norm)
    if level_info:
        sentences.append(level_info)
    if gene:
        sentences.append(f"El gen {gene} esta relacionado con la regulacion de este biomarcador.")
    return finalize(sentences)


def build_biometric_description(norm: str, gene: Optional[str]) -> str:
    key = detect_pattern_key(norm, BIOMETRIC_PATTERNS)
    sentences = list(BIOMETRIC_INFO.get(key, []))
    if not sentences:
        sentences.append("Este resultado describe una caracteristica fisiologica medible del organismo.")
        sentences.append("Estas medidas pueden variar entre personas y reflejan procesos metabolicos.")
    level_info = level_sentence(norm)
    if level_info:
        sentences.append(level_info)
    if gene:
        sentences.append(f"El gen {gene} participa en rutas biologicas relacionadas con este rasgo.")
    return finalize(sentences)


def build_trait_description(norm: str, gene: Optional[str]) -> str:
    key = detect_pattern_key(norm, TRAIT_PATTERNS) or "generic"
    sentences = list(TRAIT_INFO.get(key, TRAIT_INFO["generic"]))
    level_info = level_sentence(norm)
    if level_info:
        sentences.append(level_info)
    if gene:
        sentences.append(f"El gen {gene} participa en rutas biologicas relacionadas con este rasgo.")
    return finalize(sentences)


def build_description(phenotype_name: str) -> str:
    if not phenotype_name or phenotype_name.strip().upper() == "N/D":
        return "N/D"
    base, gene = split_gene(phenotype_name)
    norm = normalize(base)
    if detect_condition_key(norm):
        return build_condition_description(norm, gene)
    if (gene and gene.upper() in PHARMA_GENES) or any(word in norm for word in PHARMA_KEYWORDS):
        return build_pharma_description(norm, gene)
    if detect_pattern_key(norm, BIOMARKER_PATTERNS):
        return build_biomarker_description(norm, gene)
    if detect_pattern_key(norm, BIOMETRIC_PATTERNS):
        return build_biometric_description(norm, gene)
    return build_trait_description(norm, gene)


class Command(BaseCommand):
    help = "Refresh phenotype_description for rsid_extra_info with detailed templates."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show how many rows would change.")
        parser.add_argument("--limit", type=int, default=None, help="Limit number of rows processed.")
        parser.add_argument("--only-empty", action="store_true", help="Only fill rows with empty or N/D description.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]
        only_empty = options["only_empty"]

        qs = RsidExtraInfo.objects.all()
        if only_empty:
            qs = qs.filter(phenotype_description__in=["", "N/D", None])
        if limit:
            qs = qs[:limit]

        updated = 0
        batch: list[RsidExtraInfo] = []
        for row in qs.iterator():
            new_description = build_description(row.phenotype_name)
            if row.phenotype_description != new_description:
                row.phenotype_description = new_description
                batch.append(row)
            if len(batch) >= 500:
                if not dry_run:
                    RsidExtraInfo.objects.bulk_update(batch, ["phenotype_description"])
                updated += len(batch)
                batch.clear()

        if batch:
            if not dry_run:
                RsidExtraInfo.objects.bulk_update(batch, ["phenotype_description"])
            updated += len(batch)

        if dry_run:
            self.stdout.write(self.style.WARNING(f"Dry run: {updated} rows would be updated."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Updated {updated} rows."))
