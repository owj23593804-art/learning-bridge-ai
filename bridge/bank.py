from dataclasses import dataclass
from fractions import Fraction
import re


@dataclass(frozen=True)
class Problem:
    id: str
    concept: str
    prompt: str
    answer: str
    hint: str
    explanation: str
    format: str = "fraction"


CONCEPTS = {
    "meaning": "분수의 의미",
    "compare": "분수 크기 비교",
    "reduce": "약분",
    "common": "통분",
    "add": "분수의 덧셈",
    "subtract": "분수의 뺄셈",
}
PREREQUISITES = {
    "compare": "meaning", "reduce": "meaning", "common": "reduce",
    "add": "common", "subtract": "common",
}

DIAGNOSTIC = (
    Problem("d1", "meaning", "피자를 똑같이 8조각으로 나눴어요. 그중 3조각은 전체의 얼마인가요?", "3/8", "전체 조각 수를 분모에, 고른 조각 수를 분자에 써요.", "전체가 8조각이고 3조각을 골랐으므로 3/8이에요."),
    Problem("d2", "meaning", "5/9에서 분모는 얼마인가요?", "9", "분모는 분수에서 아래에 있는 수예요.", "5/9에서 아래에 있는 수 9가 분모예요.", "integer"),
    Problem("d3", "compare", "2/7과 5/7 중 더 큰 분수는 무엇인가요?", "5/7", "분모가 같으면 분자가 큰 분수가 더 커요.", "일곱 조각 중 5조각이 2조각보다 많으므로 5/7이 더 커요."),
    Problem("d4", "compare", "3/4와 3/8 중 더 큰 분수는 무엇인가요?", "3/4", "조각 수가 같다면 한 조각이 더 큰 쪽을 찾아요.", "전체를 4등분한 조각은 8등분한 조각보다 커서 3/4가 더 커요."),
    Problem("d5", "reduce", "6/8을 더 이상 약분할 수 없는 분수로 나타내세요.", "3/4", "6과 8을 함께 나눌 수 있는 수를 찾아요.", "6과 8을 각각 2로 나누면 3/4예요.", "reduced"),
    Problem("d6", "common", "2/3을 분모가 12인 분수로 나타내세요.", "8/12", "3에 얼마를 곱하면 12가 될까요?", "분모와 분자에 각각 4를 곱하면 8/12예요.", "exact"),
    Problem("d7", "add", "2/9 + 4/9는 얼마인가요?", "2/3", "분모를 그대로 두고 분자끼리 더해요.", "2/9 + 4/9 = 6/9이고, 약분하면 2/3이에요."),
    Problem("d8", "add", "1/2 + 1/4는 얼마인가요?", "3/4", "분모를 4로 맞춘 다음 더해요.", "1/2 = 2/4이므로 2/4 + 1/4 = 3/4예요."),
    Problem("d9", "subtract", "5/8 - 1/8은 얼마인가요?", "1/2", "분모를 그대로 두고 분자끼리 빼요.", "5/8 - 1/8 = 4/8이고, 약분하면 1/2예요."),
    Problem("d10", "subtract", "5/6 - 1/3은 얼마인가요?", "1/2", "1/3을 분모가 6인 분수로 바꿔 보세요.", "1/3 = 2/6이므로 5/6 - 2/6 = 3/6 = 1/2예요."),
)

PRACTICE = (
    Problem("p1", "meaning", "초콜릿을 똑같이 10조각으로 나눴어요. 7조각은 전체의 얼마인가요?", "7/10", "전체 조각 수가 분모예요.", "전체 10조각 중 7조각은 7/10이에요."),
    Problem("p2", "meaning", "4/11에서 분자는 얼마인가요?", "4", "분자는 분수에서 위에 있는 수예요.", "4/11의 위에 있는 수 4가 분자예요.", "integer"),
    Problem("p3", "compare", "4/9와 7/9 중 더 큰 분수는 무엇인가요?", "7/9", "두 분수의 분모가 같아요. 분자를 비교해요.", "아홉 조각 중 7조각이 4조각보다 많아서 7/9가 더 커요."),
    Problem("p4", "compare", "2/3과 2/5 중 더 큰 분수는 무엇인가요?", "2/3", "똑같은 전체를 적게 나눌수록 한 조각이 커요.", "3등분한 조각이 5등분한 조각보다 커서 2/3이 더 커요."),
    Problem("p5", "reduce", "8/12를 더 이상 약분할 수 없는 분수로 나타내세요.", "2/3", "8과 12를 함께 나눌 수 있는 수를 찾아요.", "분자와 분모를 각각 4로 나누면 2/3이에요.", "reduced"),
    Problem("p6", "reduce", "9/15를 더 이상 약분할 수 없는 분수로 나타내세요.", "3/5", "9와 15는 모두 3의 배수예요.", "9와 15를 각각 3으로 나누면 3/5예요.", "reduced"),
    Problem("p7", "common", "3/5를 분모가 15인 분수로 나타내세요.", "9/15", "분모 5에 곱하는 수를 분자에도 곱해요.", "5에 3을 곱하면 15예요. 3에도 3을 곱해서 9/15예요.", "exact"),
    Problem("p8", "common", "2/7을 분모가 21인 분수로 나타내세요.", "6/21", "7에 얼마를 곱하면 21이 될까요?", "분자와 분모에 각각 3을 곱하면 6/21이에요.", "exact"),
    Problem("p9", "add", "1/3 + 1/6은 얼마인가요?", "1/2", "1/3을 분모가 6인 분수로 바꿔요.", "1/3 = 2/6이므로 2/6 + 1/6 = 3/6 = 1/2예요."),
    Problem("p10", "add", "1/5 + 2/5는 얼마인가요?", "3/5", "같은 크기의 조각을 몇 개 모았나요?", "분모 5는 그대로 두고 분자 1과 2를 더하면 3/5예요."),
    Problem("p11", "subtract", "7/10 - 2/5는 얼마인가요?", "3/10", "2/5를 분모가 10인 분수로 바꿔요.", "2/5 = 4/10이므로 7/10 - 4/10 = 3/10이에요."),
    Problem("p12", "subtract", "7/9 - 4/9는 얼마인가요?", "1/3", "같은 크기의 조각 개수를 빼요.", "7/9 - 4/9 = 3/9 = 1/3이에요."),
)

BY_ID = {problem.id: problem for problem in (*DIAGNOSTIC, *PRACTICE)}
ANSWER_PATTERN = re.compile(r"([0-9]{1,6})(?:\s*/\s*([0-9]{1,6}))?", re.ASCII)


def parse_answer(answer):
    match = ANSWER_PATTERN.fullmatch(answer.strip())
    if match is None:
        raise ValueError("숫자 또는 3/4 같은 분수로 써 주세요.")
    numerator = int(match[1])
    denominator = int(match[2]) if match[2] is not None else 1
    if denominator == 0:
        raise ValueError("분모는 0보다 커야 해요.")
    return numerator, denominator, match[2] is not None


def grade(problem, answer):
    numerator, denominator, has_slash = parse_answer(answer)
    value = Fraction(numerator, denominator)
    if value != Fraction(problem.answer):
        return False
    if problem.format == "integer":
        return not has_slash
    if problem.format == "exact":
        return has_slash and denominator == int(problem.answer.split("/")[1])
    if problem.format == "reduced":
        return (numerator, denominator) == (value.numerator, value.denominator)
    return True
