import sys
import os
import json
from io import StringIO
from crewai import Agent, Task, Crew, Process
from langchain_groq import ChatGroq


# Create a custom output stream
class TeeStream(StringIO):
    def __init__(self, filename):
        super().__init__()
        self.filename = filename
        self.file = open(filename, 'w')
        self.stdout = sys.stdout

    def write(self, s):
        self.file.write(s)
        self.stdout.write(s)
        self.file.flush()
        self.stdout.flush()  # Ensure the prompt is displayed immediately

    def flush(self):
        self.file.flush()
        self.stdout.flush()

    def close(self):
        self.file.close()
        super().close()



# Redirect stdout to our custom stream
sys.stdout = TeeStream('investigation_log.txt')

# Load setups from the setups.json file
with open('setups.json', 'r') as f:
  setups = json.load(f)

# Ask the user to specify a setup_id
setup_id = input("Enter the setup_id (e.g., '1a', '2b'): ")

# Find the setup with the specified setup_id
setup = next((s for s in setups if s['setup_id'] == setup_id), None)

if setup is None:
  print(f"Setup with id '{setup_id}' not found.")
  sys.exit(1)

# Get API keys from environment variables
AGENT1_API_KEY = os.environ.get('AGENT1_API_KEY')
AGENT2_API_KEY = os.environ.get('AGENT2_API_KEY')
MODEL1_NAME = 'llama-3.1-70b-versatile'
MODEL2_NAME = 'llama-3.1-70b-versatile'

if not AGENT1_API_KEY or not AGENT2_API_KEY:
  print("API keys not found in environment variables.")
  sys.exit(1)

# Oracle LLM setup (Memoryless)
oracle_llm = ChatGroq(temperature=0,
                      groq_api_key=AGENT1_API_KEY,
                      model_name=MODEL1_NAME)


def ask_oracle(question: str, oracle_setup) -> str:
  prompt = f"""{oracle_setup['backstory']}
Question: {question}
Your response:"""
  response = oracle_llm.invoke(prompt)
  return response.content


# Investigator Agent
investigator_llm = ChatGroq(temperature=0,
                            groq_api_key=AGENT2_API_KEY,
                            model_name=MODEL2_NAME)

investigator = Agent(role=setup['agent2']['role'],
                     goal=setup['agent2']['goal'],
                     backstory=setup['agent2']['backstory'],
                     verbose=True,
                     allow_delegation=False,
                     llm=investigator_llm)

# Task for the investigator
investigation_task = Task(description=setup['agent2']['task'],
                          agent=investigator,
                          expected_output=setup['agent2']['expected_output'])

# Crew setup
crew = Crew(agents=[investigator],
            tasks=[investigation_task],
            verbose=True,
            process=Process.sequential)

# Main execution
if __name__ == "__main__":
  investigation_log = []
  max_iterations = 5
  for i in range(max_iterations):
    result = crew.kickoff()
    print(f"Investigator: {result}")

    # Ask the oracle (memoryless agent)
    oracle_response = ask_oracle(result, setup['agent1'])
    print(f"Oracle: {oracle_response}")

    # Log the interaction
    investigation_log.append(f"Q: {result}\nA: {oracle_response}\n")

    # Update the task with the new information
    investigation_task.description += f"\n\nPrevious interaction:\n{investigation_log[-1]}"

  if i == max_iterations - 1:
    print("Maximum iterations reached. Forcing final guess...")
  final_task = Task(
      description=
      f"Based on all the information gathered:\n{''.join(investigation_log)}\nMake your final guess. Start your response with 'FINAL GUESS:'.",
      agent=investigator,
      expected_output=setup['agent2']['expected_output']  # Add this line
  )
  final_result = Crew(agents=[investigator],
                      tasks=[final_task],
                      verbose=True,
                      process=Process.sequential).kickoff()
  print(f"Final Result: {final_result}")
