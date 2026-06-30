"""Skill canonicalization — maps raw skill strings to canonical names.

Strategy:
  1. Exact match (case-insensitive) against reverse synonym map.
  2. Fuzzy match via rapidfuzz if exact match misses (threshold configurable).
  3. Return title-cased original if no match — never drops unknown skills.
"""

from __future__ import annotations

from rapidfuzz import fuzz, process

# Canonical name → known synonyms / aliases.
SKILL_SYNONYMS: dict[str, list[str]] = {
    "Python": ["python", "python3", "python 3", "py", "python2"],
    "JavaScript": ["javascript", "js", "java script", "ecmascript", "es6", "es2015"],
    "TypeScript": ["typescript", "ts"],
    "React": ["react", "reactjs", "react.js", "react js", "reactjs.org"],
    "Angular": ["angular", "angularjs", "angular.js", "angular 2+"],
    "Vue.js": ["vue", "vuejs", "vue.js"],
    "Node.js": ["node", "nodejs", "node.js", "node js"],
    "Java": ["java", "java8", "java 8", "java11", "java 11"],
    "Kotlin": ["kotlin"],
    "Swift": ["swift"],
    "Go": ["golang", "go lang", "go programming"],
    "Rust": ["rust", "rust lang"],
    "C++": ["c++", "cpp", "c plus plus"],
    "C#": ["c#", "csharp", "c sharp", ".net", "dotnet"],
    "PHP": ["php"],
    "Ruby": ["ruby", "ruby on rails", "rails"],
    "Scala": ["scala"],
    "SQL": ["sql", "mysql", "postgresql", "postgres", "sqlite", "oracle sql", "t-sql", "pl/sql"],
    "NoSQL": ["nosql", "mongodb", "mongo", "cassandra", "couchdb", "dynamodb"],
    "Machine Learning": ["ml", "machine learning", "machinelearning", "supervised learning"],
    "Deep Learning": ["dl", "deep learning", "deeplearning", "neural networks", "nn"],
    "Data Science": ["data science", "datascience", "data analysis", "data analytics"],
    "NLP": ["nlp", "natural language processing", "text mining"],
    "Computer Vision": ["computer vision", "cv", "image processing", "object detection"],
    "Docker": ["docker", "containerization", "containers"],
    "Kubernetes": ["k8s", "kubernetes", "k8", "container orchestration"],
    "AWS": ["aws", "amazon web services", "amazon aws", "ec2", "s3", "lambda"],
    "GCP": ["gcp", "google cloud", "google cloud platform"],
    "Azure": ["azure", "microsoft azure"],
    "Terraform": ["terraform", "iac", "infrastructure as code"],
    "Git": ["git", "github", "gitlab", "bitbucket", "version control"],
    "CI/CD": ["ci/cd", "cicd", "ci cd", "continuous integration", "continuous deployment", "jenkins", "github actions"],
    "REST API": ["rest", "restful", "rest api", "restful api", "api design"],
    "GraphQL": ["graphql", "gql"],
    "Microservices": ["microservices", "micro services", "service mesh"],
    "Agile": ["agile", "scrum", "kanban", "sprint"],
    "Linux": ["linux", "unix", "ubuntu", "centos", "debian"],
    "Django": ["django"],
    "Flask": ["flask"],
    "FastAPI": ["fastapi", "fast api"],
    "Spring": ["spring", "spring boot", "springboot"],
    "TensorFlow": ["tensorflow", "tf"],
    "PyTorch": ["pytorch", "torch"],
    "Pandas": ["pandas"],
    "NumPy": ["numpy", "np"],
    "Spark": ["apache spark", "spark", "pyspark"],
    "Kafka": ["apache kafka", "kafka"],
    "Redis": ["redis"],
    "Elasticsearch": ["elasticsearch", "elastic search", "elk", "opensearch"],
}

# Build reverse lookup: synonym_lower → canonical
_REVERSE: dict[str, str] = {}
for _canonical, _synonyms in SKILL_SYNONYMS.items():
    _REVERSE[_canonical.lower()] = _canonical
    for _syn in _synonyms:
        _REVERSE[_syn.lower()] = _canonical


def normalize_skill(raw: str, fuzzy_threshold: int = 88) -> str:
    """
    Return canonical skill name for a raw skill string.

    Never returns None — unknown skills are preserved (title-cased) at lower confidence.
    """
    if not raw or not raw.strip():
        return raw or ""

    cleaned = raw.strip()
    lower = cleaned.lower()

    # Exact match
    if lower in _REVERSE:
        return _REVERSE[lower]

    # Fuzzy match against all known synonyms
    result = process.extractOne(
        lower,
        list(_REVERSE.keys()),
        scorer=fuzz.token_set_ratio,
        score_cutoff=fuzzy_threshold,
    )
    if result:
        return _REVERSE[result[0]]

    # Unknown — preserve as title-case if fully lowercase input
    return cleaned.title() if cleaned == cleaned.lower() else cleaned


def skills_are_duplicate(a: str, b: str) -> bool:
    """Return True if two skill strings map to the same canonical name."""
    return normalize_skill(a) == normalize_skill(b)
