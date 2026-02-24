from src.models.loan_file import LoanFile
from src.crew import LoanOperationsCrew
import json

with open("sample_loans/LOAN001.json") as f:
    data = json.load(f)

loan = LoanFile(**data)
crew = LoanOperationsCrew(loan)
result = crew.run()
print(result)
