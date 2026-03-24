#!/usr/bin/env python3

import datetime
import os
from pathlib import Path

def generate_status():
    """Generate current status report for the onboarding process."""
    
    # Get current timestamp
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    
    # Read the current onboarding plan to check progress
    onboarding_plan_path = Path("onboarding_plan.md")
    completed_tasks = 0
    total_tasks = 0
    
    if onboarding_plan_path.exists():
        with open(onboarding_plan_path, 'r') as f:
            content = f.read()
            
        # Count checklist items
        for line in content.split('\n'):
            if '- [x]' in line:
                completed_tasks += 1
            elif '- [ ]' in line:
                total_tasks += 1
            
        # Add incomplete tasks from the last section to total
        total_tasks += completed_tasks
    
    # Calculate completion percentage
    completion_percentage = 0
    if total_tasks > 0:
        completion_percentage = int((completed_tasks / total_tasks) * 100)
    
    # Create status content
    status_content = f"# STATUS.md\n\n**Last Updated:** {timestamp}\n\n## Current Focus\nImplementing regular progress reporting and optimizing onboarding workflow.\n\n## Active Tasks\n- Implement regular status summaries\n- Complete initial onboarding process\n- Establish continuous improvement cycle\n\n## Recent Progress\n- ✅ Created comprehensive onboarding documentation\n- ✅ Defined user goals in GOALS.md\n- ✅ Initialized git version control\n- ✅ Established feedback mechanism\n\n## Next Immediate Steps\n- Create script for automated status updates\n- Implement scheduled reporting\n- Finalize onboarding completion\n\n## Notable Events\n- Onboarding process is {completion_percentage}% complete\n- All foundational systems are in place\n\n## Notes\nAll progress is being committed to the git repository for full transparency and history tracking."
    
    # Write to STATUS.md
    status_path = Path("STATUS.md")
    with open(status_path, 'w') as f:
        f.write(status_content)
    
    # Add to git
    os.system("git add STATUS.md")
    
    print(f"Status report generated and saved to {status_path}")

if __name__ == "__main__":
    generate_status()