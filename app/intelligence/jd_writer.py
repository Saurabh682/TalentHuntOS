"""Smart Job Description writer with bias detection, debiasing, and AI generation for TalentHunt OS."""

from dataclasses import dataclass, field, asdict
import re
import logging
from typing import List, Dict, Any, Optional

from app.ai.engine import ai_engine

logger = logging.getLogger("talenthunt.intelligence.jd_writer")


@dataclass
class JDBiasAnalysis:
    """Bias and inclusivity analysis results for Job Descriptions."""
    overall_bias_score: float  # 0.0 (inclusive) to 1.0 (highly biased)
    gender_bias_score: float  # 0.0 to 1.0
    age_bias_score: float  # 0.0 to 1.0
    jargon_score: float  # 0.0 to 1.0
    flagged_terms: List[Dict[str, str]] = field(default_factory=list)
    inclusivity_rating: str = "Inclusive & Welcoming"
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize analysis to dictionary."""
        return asdict(self)


# Biased & Non-Inclusive Language Dictionaries with Replacements
BIAS_DICTIONARY = {
    # Masculine-coded terms
    "rockstar": {"category": "gender_masculine", "replacement": "skilled professional", "reason": "Aggressive masculine-coded tech jargon."},
    "ninja": {"category": "gender_masculine", "replacement": "specialist", "reason": "Exclusionary tech jargon."},
    "guru": {"category": "gender_masculine", "replacement": "expert", "reason": "Jargon that may discourage qualified candidates."},
    "dominant": {"category": "gender_masculine", "replacement": "leading", "reason": "Masculine-coded competitive term."},
    "aggressive": {"category": "gender_masculine", "replacement": "ambitious", "reason": "Masculine-coded aggressive language."},
    "workaholic": {"category": "gender_masculine", "replacement": "dedicated", "reason": "Promotes unhealthy work expectation."},
    "fearless": {"category": "gender_masculine", "replacement": "confident", "reason": "Masculine-coded descriptor."},
    "hacker": {"category": "gender_masculine", "replacement": "engineer", "reason": "Informal jargon."},
    "manpower": {"category": "gender_masculine", "replacement": "workforce / team size", "reason": "Gender-exclusive noun."},
    "chairman": {"category": "gender_masculine", "replacement": "chairperson", "reason": "Gender-exclusive noun."},
    
    # Ageist terms
    "digital native": {"category": "ageism", "replacement": "tech-savvy professional", "reason": "Ageist term targeting younger demographics."},
    "recent graduate": {"category": "ageism", "replacement": "early-career candidate", "reason": "Ageist requirement excluding career changers."},
    "youthful team": {"category": "ageism", "replacement": "dynamic team", "reason": "Explicit age discrimination risk."},
    "energetic environment": {"category": "ageism", "replacement": "vibrant environment", "reason": "Implicit age bias term."},
    "overqualified": {"category": "ageism", "replacement": "highly experienced", "reason": "Ageist barrier term."},
    
    # Exclusionary jargon / unrealistic demands
    "hit the ground running": {"category": "jargon", "replacement": "contribute quickly with onboarding support", "reason": "Overused jargon implying lack of training."},
    "work hard play hard": {"category": "jargon", "replacement": "collaborative and rewarding culture", "reason": "Vague culture phrase associated with burnout."},
    "flawless track record": {"category": "jargon", "replacement": "proven track record", "reason": "Unrealistic perfectionist framing."},
    "must have 10+ years": {"category": "jargon", "replacement": "extensive experience in", "reason": "Arbitrary experience cap."},
}


def analyze_jd_bias(jd_text: str) -> JDBiasAnalysis:
    """Analyze Job Description text for gender bias, ageism, and exclusionary jargon."""
    if not jd_text or not jd_text.strip():
        return JDBiasAnalysis(
            overall_bias_score=0.0,
            gender_bias_score=0.0,
            age_bias_score=0.0,
            jargon_score=0.0,
            flagged_terms=[],
            inclusivity_rating="Inclusive & Welcoming",
            recommendations=["Job description text is empty."],
        )

    text_lower = jd_text.lower()
    flagged: List[Dict[str, str]] = []
    
    gender_count = 0
    age_count = 0
    jargon_count = 0

    for term, meta in BIAS_DICTIONARY.items():
        pattern = r'\b' + re.escape(term) + r'\b'
        matches = re.findall(pattern, text_lower)
        if matches:
            count = len(matches)
            if meta["category"] == "gender_masculine":
                gender_count += count
            elif meta["category"] == "ageism":
                age_count += count
            elif meta["category"] == "jargon":
                jargon_count += count

            flagged.append({
                "term": term,
                "occurrences": str(count),
                "category": meta["category"],
                "reason": meta["reason"],
                "suggested_replacement": meta["replacement"],
            })

    total_words = max(1, len(text_lower.split()))
    
    # Calculate scores normalized between 0.0 and 1.0
    gender_score = round(min(1.0, (gender_count * 20.0) / total_words), 2)
    age_score = round(min(1.0, (age_count * 25.0) / total_words), 2)
    jargon_score = round(min(1.0, (jargon_count * 15.0) / total_words), 2)

    overall_bias = round(min(1.0, (gender_score * 0.45) + (age_score * 0.35) + (jargon_score * 0.20)), 2)

    if overall_bias == 0.0:
        rating = "Inclusive & Welcoming"
    elif overall_bias < 0.25:
        rating = "Low Bias Risk"
    elif overall_bias < 0.60:
        rating = "Moderate Bias Risk"
    else:
        rating = "High Bias Risk - Requires Debiasing"

    recs = []
    if gender_count > 0:
        recs.append("Replace masculine-coded terms (e.g., 'rockstar', 'ninja', 'aggressive') with inclusive role descriptors.")
    if age_count > 0:
        recs.append("Remove age-specific phrases (e.g., 'digital native', 'recent graduate') to welcome diverse experience levels.")
    if jargon_count > 0:
        recs.append("Simplify corporate jargon and replace extreme requirements with realistic growth expectations.")
    if not recs:
        recs.append("Great job! The Job Description follows modern inclusive hiring standards.")

    return JDBiasAnalysis(
        overall_bias_score=overall_bias,
        gender_bias_score=gender_score,
        age_bias_score=age_score,
        jargon_score=jargon_score,
        flagged_terms=flagged,
        inclusivity_rating=rating,
        recommendations=recs,
    )


def debias_jd(jd_text: str) -> str:
    """Automatically replace biased and exclusionary terms with inclusive alternatives."""
    if not jd_text:
        return ""

    debiased = jd_text
    for term, meta in BIAS_DICTIONARY.items():
        pattern = re.compile(r'(?<!\w)' + re.escape(term) + r'(?!\w)', re.IGNORECASE)
        replacement = meta["replacement"]
        
        # Match case of original term
        def replace_match(m):
            txt = m.group(0)
            if txt.isupper():
                return replacement.upper()
            elif txt.istitle():
                return replacement.title()
            elif txt and txt[0].isupper():
                return replacement.capitalize()
            return replacement

        debiased = pattern.sub(replace_match, debiased)

    return debiased


def generate_optimized_jd(
    role_title: str,
    department: str,
    key_responsibilities: List[str],
    required_skills: List[str],
    preferred_skills: Optional[List[str]] = None,
    culture_values: Optional[List[str]] = None,
    remote_policy: str = "Hybrid",
    salary_range: Optional[str] = None,
) -> str:
    """Generate a clean, non-biased, high-converting Job Description using AI Engine with fallback."""
    prompt = (
        f"Generate an engaging, highly inclusive, non-biased Job Description for the following role:\n"
        f"Role Title: {role_title}\n"
        f"Department: {department}\n"
        f"Work Model: {remote_policy}\n"
        f"Salary Range: {salary_range or 'Competitive'}\n"
        f"Key Responsibilities:\n" + "\n".join(f"- {r}" for r in key_responsibilities) + "\n"
        f"Required Skills:\n" + "\n".join(f"- {s}" for s in required_skills) + "\n"
    )
    if preferred_skills:
        prompt += f"Preferred Skills:\n" + "\n".join(f"- {s}" for s in preferred_skills) + "\n"
    if culture_values:
        prompt += f"Culture & Values:\n" + "\n".join(f"- {v}" for v in culture_values) + "\n"

    system_prompt = (
        "You are an expert HR Talent Acquisition Specialist and Diversity & Inclusion Consultant. "
        "Create structured, clear, and bias-free job descriptions. Avoid gendered jargon, ageist terms, "
        "or exclusionary demands. Use sections: Role Overview, What You Will Do, What We Are Looking For, "
        "Nice to Haves, and What We Offer."
    )

    try:
        response = ai_engine.generate_response(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.6,
        )
        if response and len(response.strip()) > 100:
            return response
    except Exception as e:
        logger.warning(f"AI Engine JD generation fallback due to: {e}")

    # Structured Template Fallback
    resp_bullets = "\n".join(f"• {r}" for r in key_responsibilities)
    req_bullets = "\n".join(f"• {s}" for s in required_skills)
    pref_bullets = "\n".join(f"• {s}" for s in (preferred_skills or [])) or "• Passion for learning and technology."

    fallback_jd = f"""# {role_title}

**Department:** {department}  
**Work Model:** {remote_policy}  
**Compensation:** {salary_range or 'Competitive Salary + Benefits'}

---

### Role Overview
We are looking for a collaborative, impact-driven **{role_title}** to join our team. In this role, you will help design, build, and scale core systems while working closely with cross-functional team members in a supportive and growth-oriented environment.

### Key Responsibilities
{resp_bullets}

### What We Are Looking For
{req_bullets}

### Nice to Have
{pref_bullets}

### Diversity & Inclusion Statement
We are an equal opportunity employer committed to fostering an inclusive and diverse environment. Candidates of all backgrounds, gender identities, ages, and abilities are strongly encouraged to apply.
"""
    return fallback_jd


def enhance_jd(existing_jd: str, target_improvements: Optional[List[str]] = None) -> Dict[str, Any]:
    """Analyze existing JD, debias text, generate improved version, and return comprehensive report."""
    analysis = analyze_jd_bias(existing_jd)
    debiased_text = debias_jd(existing_jd)

    # Attempt AI enhancement if requested
    enhanced_version = debiased_text
    try:
        prompt = (
            f"Refine and enhance the following job description to be clear, engaging, and fully inclusive:\n\n"
            f"{debiased_text}\n"
        )
        if target_improvements:
            prompt += f"\nTarget Focus Areas: {', '.join(target_improvements)}"
            
        enhanced_version = ai_engine.generate_response(
            prompt=prompt,
            system_prompt="You are an expert HR Job Description Editor. Return an updated, professional, clean Job Description.",
            temperature=0.5,
        )
    except Exception as e:
        logger.debug(f"AI JD enhancement fallback: {e}")

    post_analysis = analyze_jd_bias(enhanced_version)

    return {
        "original_jd": existing_jd,
        "debiased_jd": debiased_text,
        "enhanced_jd": enhanced_version,
        "pre_bias_analysis": analysis.to_dict(),
        "post_bias_analysis": post_analysis.to_dict(),
        "bias_reduction_pct": int(max(0.0, (analysis.overall_bias_score - post_analysis.overall_bias_score) * 100)),
    }
