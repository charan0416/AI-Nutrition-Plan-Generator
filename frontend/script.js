// frontend/script.js
// This script interacts with the backend API

// TODO: Get backend URL from a configuration or environment variable
// For local testing, keep it hardcoded
const BACKEND_URL = 'http://127.0.0.1:8001'; // Changed to match the server port // Or http://localhost:8000 if that's where your FastAPI runs'; // Or http://localhost:8000 if that's where your FastAPI runs

document.getElementById('nutrition-form').addEventListener('submit', async function(event) {
    event.preventDefault(); // Prevent default form submission

    // Get form data
    const age = parseInt(document.getElementById('age').value);
    const gender = document.getElementById('gender').value;
    const height_cm = parseFloat(document.getElementById('height_cm').value);
    const goal = document.getElementById('goal').value;
    const dietary_preference = document.getElementById('dietary_preference').value;
    const activity_level = document.getElementById('activity_level').value;
    const weight_kg = parseFloat(document.getElementById('weight_kg').value);

    // Get optional previous month's data
    const lastMonthWeight = parseFloat(document.getElementById('last_month_weight').value);
    const lastMonthBmi = parseFloat(document.getElementById('last_month_bmi').value);
    const lastMonthGoal = document.getElementById('last_month_goal').value;

    let last_month_progress = null;
    if (!isNaN(lastMonthWeight) && !isNaN(lastMonthBmi) && lastMonthGoal !== "") {
        last_month_progress = {
            last_month_weight: lastMonthWeight,
            last_month_bmi: lastMonthBmi,
            goal: lastMonthGoal
        };
    } else if (!isNaN(lastMonthWeight) || !isNaN(lastMonthBmi) || lastMonthGoal !== "") {
         // Basic validation: if *any* prev month field is filled, all should be for best results
         alert("Please fill in all three 'Previous Month\'s Progress' fields (Weight, BMI, Goal) or leave all three blank.");
         return; // Stop the submission
    }


    // Prepare data for the backend
    const postData = {
        age: age,
        gender: gender,
        height_cm: height_cm,
        goal: goal,
        dietary_preference: dietary_preference,
        activity_level: activity_level,
        weight_kg: weight_kg,
        last_month_progress: last_month_progress // Will be null if not filled
    };

    // Show loading message and hide previous results/errors
    document.getElementById('loading').classList.remove('hidden');
    document.getElementById('error-message').classList.add('hidden');
    document.getElementById('results').classList.add('hidden');
    document.getElementById('plan-details').innerHTML = ''; // Clear previous plan details

    try {
        // Send data to the backend API
        const response = await fetch(`${BACKEND_URL}/generate-plan`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(postData),
        });

        // Hide loading message
        document.getElementById('loading').classList.add('hidden');

        if (!response.ok) {
            // Handle HTTP errors (e.g., 400, 500)
            const errorData = await response.json();
            const errorMessage = errorData.detail || 'An error occurred while generating the plan.';
            document.getElementById('error-message').textContent = errorMessage;
            document.getElementById('error-message').classList.remove('hidden');
            console.error('API Error:', response.status, errorData);
            return; // Stop here if there's an error
        }

        // Parse the JSON response
        const result = await response.json();

        // Display results
        document.getElementById('result-bmi').textContent = result.bmi.toFixed(2);
        document.getElementById('result-targets').textContent = result.daily_targets;

        // Display diet plan details
        const plan = result.diet_plan; // The generated JSON plan
        if (plan && plan.overall_description) {
            document.getElementById('plan-description').textContent = plan.overall_description;
            document.getElementById('plan-macro-targets').textContent = plan.overall_macro_targets;
            document.getElementById('plan-disclaimer').textContent = plan.disclaimer;

            const planDetailsDiv = document.getElementById('plan-details');
            planDetailsDiv.innerHTML = ''; // Clear previous content

            if (plan.daily_plans && Array.isArray(plan.daily_plans)) {
                 plan.daily_plans.forEach(dayPlan => {
                    const dayDiv = document.createElement('div');
                    dayDiv.innerHTML = `
                        <h4>Day ${dayPlan.day_number}</h4>
                        <p><em>${dayPlan.daily_composition_est}</em></p>
                    `;

                    if (dayPlan.meals && Array.isArray(dayPlan.meals)) {
                        dayPlan.meals.forEach(meal => {
                            const mealDiv = document.createElement('div');
                            mealDiv.style.marginLeft = '15px'; // Indent meals
                            mealDiv.innerHTML = `
                                <h5>${meal.meal_type}</h5>
                                <p><em>${meal.meal_composition_est}</em></p>
                                <ul>
                                    ${meal.foods.map(food => `<li>${food.name} - ${food.quantity} ${food.notes ? `(${food.notes})` : ''}</li>`).join('')}
                                </ul>
                            `;
                            dayDiv.appendChild(mealDiv);
                        });
                    } else {
                         dayDiv.innerHTML += '<p>No meal details for this day.</p>';
                    }
                    planDetailsDiv.appendChild(dayDiv);
                 });
            } else {
                 planDetailsDiv.innerHTML = '<p>No daily plans found in the generated data.</p>';
            }


            document.getElementById('results').classList.remove('hidden');

        } else {
             document.getElementById('error-message').textContent = 'Generated plan data is incomplete.';
             document.getElementById('error-message').classList.remove('hidden');
             console.error('Invalid plan structure received:', plan);
        }


    } catch (error) {
        // Handle network errors or unexpected issues
        document.getElementById('loading').classList.add('hidden');
        document.getElementById('error-message').textContent = 'A network error occurred or the server is not running.';
        document.getElementById('error-message').classList.remove('hidden');
        console.error('Fetch Error:', error);
    }
});