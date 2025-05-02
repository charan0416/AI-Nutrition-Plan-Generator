# -----------------------------------------------------------------------------
# File: nutrition_web_app/backend/app.py
# Description: FastAPI backend for AI Nutrition Plan Generator
# This file contains the complete code for the backend application.
# -----------------------------------------------------------------------------

import os
import json
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

# --- Load API Key from .env file ---
# This path assumes your .env file is in the project root directory (one level up from /backend)
dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(dotenv_path=dotenv_path)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# --- Configure Google Generative AI ---
try:
    if not GOOGLE_API_KEY:
         raise ValueError("GOOGLE_API_KEY environment variable not set or found.")
    genai.configure(api_key=GOOGLE_API_KEY)
    print("INFO: Google Generative AI configured successfully.")
except Exception as e:
    print(f"FATAL ERROR: AI API Configuration Failed - {e}")
    GOOGLE_API_KEY = None

# --- Choose the AI Model ---
GEMINI_MODEL_NAME = 'gemini-1.5-flash-latest' # Or 'gemini-1.5-pro-latest'

# --- FastAPI App Initialization ---
app = FastAPI()

# --- CORS Configuration ---
origins = [
    "http://localhost",
    "http://localhost:8000",
    "http://127.0.0.1",
    "http://127.0.0.1:8000",
    "null"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # CAUTION: Change this in production!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Data Models (using Pydantic) ---
class UserProfileInput(BaseModel):
    age: int = Field(..., gt=0)
    gender: str
    height_cm: float = Field(..., gt=0)
    goal: str
    dietary_preference: str
    activity_level: str
    weight_kg: float = Field(..., gt=0)
    last_month_progress: Optional[Dict[str, Any]] = None

# --- Nutrition Logic Functions ---
NUTRI_CONFIG = {
    "calories_per_kg_base": 25,
    "activity_multipliers": {
        "sedentary": 1.2, "light": 1.375, "moderate": 1.55, "active": 1.725, "very active": 1.9
    },
    "calorie_adjustment_per_goal": {
        "weight loss": -500, "weight gain": +300, "maintain": 0
    },
    "macro_split_ratios": {
        "maintain": (0.3, 0.5, 0.2), "weight loss": (0.4, 0.4, 0.2), "weight gain": (0.3, 0.55, 0.15)
    },
    "min_calories": 1200,
}

def calculate_bmi(weight_kg: float, height_cm: float) -> float:
    if height_cm <= 0: raise ValueError("Height must be positive.")
    if weight_kg <= 0: raise ValueError("Weight must be positive.")
    height_m = height_cm / 100.0
    bmi = weight_kg / (height_m ** 2)
    return round(bmi, 2)

def estimate_daily_nutrients(user_data: dict, current_weight_kg: float) -> dict:
    age = user_data.get('age', 25)
    gender = user_data.get('gender', '').lower()
    height = user_data.get('height_cm', 165)
    activity_level = user_data.get('activity_level', 'moderate').lower()
    goal = user_data.get('goal', 'maintain').lower()

    try:
        S = 5 if gender == 'male' else -161
        if not all(isinstance(x, (int, float)) for x in [age, height, current_weight_kg]):
             print("Warning: Non-numeric age, height, or weight passed to nutrient estimation. Using fallback BMR.")
             if isinstance(current_weight_kg, (int, float)) and current_weight_kg > 0:
                 bmr = NUTRI_CONFIG["calories_per_kg_base"] * current_weight_kg
             else:
                 bmr = 2000 # Absolute fallback
        else:
             bmr = (10 * current_weight_kg) + (6.25 * height) - (5 * age) + S

        activity_multiplier = NUTRI_CONFIG['activity_multipliers'].get(activity_level, 1.55)
        tdee = bmr * activity_multiplier
        goal_adjustment = NUTRI_CONFIG['calorie_adjustment_per_goal'].get(goal, 0)
        estimated_daily_calories = int(tdee + goal_adjustment)
        estimated_daily_calories = max(estimated_daily_calories, NUTRI_CONFIG['min_calories'])

        macro_ratios = NUTRI_CONFIG['macro_split_ratios'].get(goal, NUTRI_CONFIG['macro_split_ratios']['maintain'])
        protein_g = int((estimated_daily_calories * macro_ratios[0]) / 4)
        carbs_g = int((estimated_daily_calories * macro_ratios[1]) / 4)
        fat_g = int((estimated_daily_calories * macro_ratios[2]) / 9)

        return {
            "estimated_daily_calories": estimated_daily_calories,
            "protein_g": protein_g,
            "carbs_g": carbs_g,
            "fat_g": fat_g,
            "macro_targets_str": f"Approx {estimated_daily_calories} kcal, {protein_g}g Protein, {carbs_g}g Carbs, {fat_g}g Fat"
         }
    except Exception as e:
         print(f"Error during calorie/macro calculation: {e}. Returning default estimates.")
         return {
            "estimated_daily_calories": 2000,
            "protein_g": 100,
            "carbs_g": 250,
            "fat_g": 67,
            "macro_targets_str": "Approx 2000 kcal, 100g Protein, 250g Carbs, 67g Fat (Calculation Error)"
         }

# --- AI Diet Plan Generation Function ---
def generate_diet_plan_ai(user_data: dict, current_bmi: float, daily_nutrients: dict, last_month_progress: Optional[dict] = None) -> dict:
    if GOOGLE_API_KEY is None:
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="AI API is not configured.")

    progress_notes = ""
    if last_month_progress and isinstance(last_month_progress, dict):
        last_month_weight = last_month_progress.get('last_month_weight')
        last_month_bmi = last_month_progress.get('last_month_bmi')
        last_goal = last_month_progress.get('goal')

        if last_month_weight is not None and isinstance(last_month_weight, (int, float)) and last_month_bmi is not None and isinstance(last_month_bmi, (int, float)) and last_goal is not None:
            current_weight = user_data.get('weight_kg')
            current_goal = user_data.get('goal', 'maintain').lower()

            if current_weight is not None and isinstance(current_weight, (int, float)):
                weight_change = current_weight - last_month_weight

                notes_list = [
                    f"Last month's weight was {last_month_weight:.2f} kg (BMI: {last_month_bmi:.2f}).",
                    f"Current weight is {current_weight:.2f} kg (BMI: {current_bmi:.2f}).",
                    f"User's goal last month was '{last_goal}'.",
                    f"User's current goal is '{current_goal}'.",
                    f"Weight changed by {weight_change:.2f} kg last month."
                ]

                if current_goal == 'weight loss':
                    if weight_change > 0: notes_list.append("Progress opposite to goal (gained weight). Suggest reviewing adherence and activity.")
                    elif weight_change == 0: notes_list.append("Progress stagnant (no weight change). Suggest slightly stricter adherence or increased activity.")
                    elif -0.5 <= weight_change < 0: notes_list.append("Progress slow (lost less than 0.5 kg). Reinforce consistency.")
                    elif -1.5 < weight_change < -0.5: notes_list.append("Progress good (lost 0.5-1.5 kg). Reinforce consistency and plan.")
                    elif weight_change <= -1.5: notes_list.append("Progress very fast (lost more than 1.5 kg). Suggest ensuring adequate calorie intake and professional consultation.")
                elif current_goal == 'weight gain':
                    if weight_change < 0: notes_list.append("Progress opposite to goal (lost weight). Suggest increasing calorie intake and consistency.")
                    elif weight_change == 0: notes_list.append("Progress stagnant (no weight change). Suggest increasing calorie intake.")
                    elif 0 < weight_change <= 0.25: notes_list.append("Progress slow (gained less than 0.25 kg). Reinforce consistency and suggest slightly higher intake.")
                    elif 0.25 < weight_change <= 0.5: notes_list.append("Progress good (gained 0.25-0.5 kg). Reinforce consistency and plan.")
                    elif weight_change > 0.5: notes_list.append("Progress very fast (gained more than 0.5 kg). Suggest ensuring balanced diet and potentially slightly lower intake or more focused gain.")
                else: # Maintain goal
                     if weight_change > 0.5: notes_list.append("Gained noticeable weight while aiming to maintain. Suggest reviewing calorie intake vs activity.")
                     elif weight_change < -0.5: notes_list.append("Lost noticeable weight while aiming to maintain. Suggest reviewing calorie intake vs activity.")
                     else: notes_list.append("Weight remained relatively stable, aligning with maintain goal.")

                progress_notes = "Notes based on user's progress last month:\n" + "\n".join(notes_list) + "\nConsider these notes when tailoring this month's plan."
            # else: warning about current weight missing handled by endpoint print
        # else: warning about incomplete/invalid last_month_progress handled by endpoint print
    else:
        progress_notes = "No previous progress data provided."

    prompt_text = f"""
You are an AI Personalized Diet Planning Agent for a nutrition application.
Your task is to create a realistic, varied, and healthy 1-month (30-day) daily meal plan for a user based on their detailed profile, current BMI, health goals, and dietary preference.

User Profile:
- Age: {user_data.get('age', 'N/A')}
- Gender: {user_data.get('gender', 'N/A')}
- Current BMI: {current_bmi:.2f}
- Activity Level: {user_data.get('activity_level', 'Not set')}
- Goal: {user_data.get('goal', 'Not set')}
- Dietary Preference: {user_data.get('dietary_preference', 'Not set')}

Nutritional Targets (Estimated):
- Target Daily Calories: Approximately {daily_nutrients.get('estimated_daily_calories', 'N/A')} kcal
- Target Macros: {daily_nutrients.get('macro_targets_str', 'N/A')}

Instructions:
1. Create a meal plan for exactly 30 consecutive days.
2. For EACH day, include meals like Breakfast, Lunch, and Dinner. Also include 1-2 healthy snack suggestions daily.
3. Ensure significant variety in the meals and snacks across the 30 days. Do not repeat the exact same daily plan frequently. Vary meals throughout the month.
4. ALL suggested foods and meals must strictly adhere to the user's "{user_data.get('dietary_preference', 'Not set')}" preference. Only suggest vegetarian items if preference is "Veg", and include appropriate non-vegetarian items if preference is "Non-Veg".
5. Suggest realistic portion sizes (e.g., "1 cup cooked", "150g", "2 slices").
6. Include brief notes or simple preparation ideas for each food item or meal where helpful.
7. For each meal, provide an estimated composition (e.g., "Approx 350 kcal, 15g protein, 45g carbs, 12g fat").
8. For each day, provide an estimated total daily composition (e.g., "Total: 1800 kcal, 90g protein, 220g carbs, 60g fat"). These daily totals should aim to align with the overall target daily calories and macro targets.
9. Provide an overall description of the diet plan's approach (e.g., balanced, high-protein) and reiterate the estimated daily macro targets.
10. **Agentic Adaptation based on Progress:** {progress_notes}
    Adjust suggestions or add comments if their weight change was significantly faster or slower than expected for their goal, as indicated in the progress notes. Ensure the plan acknowledges the previous month's outcome subtly. If "{progress_notes}" is empty, state that no previous progress data was processed for adaptation.
11. Include a standard health disclaimer at the end, emphasizing consultation with a healthcare professional before starting any new diet.
12. Output the entire plan as a JSON object ONLY. Do NOT include any conversational text, markdown formatting (like ```json```), or any other text outside the JSON object. The JSON should strictly follow the schema described below.

JSON Output Structure:
{{
    "overall_description": "string (brief description of the plan)",
    "overall_macro_targets": "string (e.g., 'Approx 2000 kcal, 100g Protein, 250g Carbs, 67g Fat')",
    "daily_plans": [
      {{
        "day_number": integer (1 to 30),
        "date_notes": "string (optional notes like 'Week 1, Day 3')",
        "meals": [
          {{
            "meal_type": "string (Breakfast, Mid-morning Snack, Lunch, Evening Snack, Dinner)",
            "foods": [
              {{
                "name": "string (e.g., 'Oatmeal with Berries')",
                "quantity": "string (e.g., '1 cup cooked', '50g dry')",
                "notes": "string (e.g., 'Use rolled oats, add a handful of berries')"
              }}
            ],
            "meal_composition_est": "string (e.g., 'Approx 350 kcal, 15g protein, 45g carbs, 12g fat')"
          }}
        ],
        "daily_composition_est": "string (e.g., 'Total: 1800 kcal, 90g protein, 220g carbs, 60g fat')"
      }}
    ],
    "disclaimer": "string (standard health disclaimer)"
}}
Ensure the JSON is valid and complete for 30 days.
"""
    try:
        model = genai.GenerativeModel(GEMINI_MODEL_NAME)
        response = model.generate_content(
            prompt_text, # Use the f-string formatted prompt
            generation_config=genai.GenerationConfig(
                temperature=0.8,
                response_mime_type='application/json'
            )
        )
        plan_json_string = response.text
        plan_data = json.loads(plan_json_string)
        return plan_data
    except json.JSONDecodeError as e:
        print(f"Error parsing AI response JSON: {e}")
        print(f"AI Response content (might not be valid JSON): {plan_json_string}")
        truncated_content = plan_json_string[:500] + "..." if len(plan_json_string) > 500 else plan_json_string
        raise HTTPException(status_code=500, detail=f"AI response was not valid JSON. Content: {truncated_content}")
    except Exception as e:
        print(f"An unexpected error occurred during Google AI diet generation: {e}")
        raise HTTPException(status_code=500, detail=f"AI generation failed: {e}")

# --- FastAPI Endpoint ---
@app.post("/generate-plan")
async def generate_plan_endpoint(user_input: UserProfileInput):
    print("\nReceived request to generate plan.")
    if GOOGLE_API_KEY is None:
         print("ERROR: API Key is not configured. Returning 500.")
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="AI API Key is not configured. Cannot generate plan.")

    try:
        current_bmi = calculate_bmi(user_input.weight_kg, user_input.height_cm)
        print(f"Calculated BMI: {current_bmi}")

        user_data_dict = user_input.model_dump()
        daily_nutrients = estimate_daily_nutrients(user_data_dict, user_input.weight_kg)
        print(f"Estimated daily nutrients: {daily_nutrients.get('macro_targets_str', 'N/A')}")

        diet_plan = generate_diet_plan_ai(user_data_dict, current_bmi, daily_nutrients, user_input.last_month_progress)
        print("AI plan generation function called and returned.")

        return {
            "bmi": current_bmi,
            "daily_targets": daily_nutrients.get('macro_targets_str', 'N/A'),
            "diet_plan": diet_plan
        }

    except ValueError as e:
        print(f"ValueError during plan generation: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    except HTTPException as e:
        print(f"HTTPException during plan generation: {e.detail}")
        raise e

    except Exception as e:
        print(f"An unexpected error occurred in the /generate-plan endpoint: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="An unexpected error occurred during plan generation. Please try again later.")

# Optional: Root endpoint (responds to GET /)
@app.get("/")
async def read_root():
    print("Received GET request at /")
    return {"message": "Nutrition App Backend is running. Access /generate-plan via POST."}

# Add a dummy endpoint to test Pydantic validation and basic request receiving
@app.post("/test-input")
async def test_input(user_input: UserProfileInput):
    print("\nReceived test input:")
    print(user_input.model_dump_json(indent=2))
    return {"message": "Input received and validated successfully!", "your_data": user_input}