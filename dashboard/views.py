from django.shortcuts import render, redirect
import numpy as np
import pandas as pd
import requests
from django.http import JsonResponse
from sklearn.preprocessing import MinMaxScaler

from django.contrib import messages
from django.contrib.auth import logout
import time
from .firebase import *  
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from sklearn.metrics import r2_score
import os
from google.oauth2 import service_account
from django.conf import settings
from django.contrib import messages
from django.shortcuts import render, redirect
from .firebase import db
from django.conf import settings
import base64
from django.core.cache import cache
import threading
from django.contrib.sessions.backends.db import SessionStore


def get_sales_list():
    sales_data = cache.get('sales_list')
    if sales_data is not None:
        return sales_data
    try:
        docs = db.collection('sales_data').stream()
        sales_data = [doc.to_dict() for doc in docs]
        cache.set('sales_list', sales_data, timeout=900)
        return sales_data
    except Exception as e:
        print(f"Error loading sales: {e}")
        return []

def get_products_list():
    products_data = cache.get('products_list')
    if products_data is not None:
        return products_data
    try:
        docs = db.collection('products').stream()
        products_data = [doc.to_dict() for doc in docs]
        cache.set('products_list', products_data, timeout=900)
        return products_data
    except Exception as e:
        print(f"Error loading products: {e}")
        return []

def get_sales_dataframe():
    df = cache.get('sales_dataframe')
    if df is not None:
        return df
    
    try:
        data = get_sales_list()
        df = pd.DataFrame(data)
        cache.set('sales_dataframe', df, timeout=900)  # Cache for 15 minutes
        return df
    except Exception as e:
        print(f"Error loading Firestore data: {e}")
        return pd.DataFrame()



# Function to prepare data for LSTM
def prepare_data(series, look_back=7):
    X, y = [], []
    for i in range(len(series) - look_back):
        X.append(series[i:(i + look_back)])
        y.append(series[i + look_back])
    return np.array(X), np.array(y)

# Function to train and predict using LSTM
def train_predict_lstm(data, look_back=7, epochs=50, batch_size=8, next_days=1):
    # Lazy load massive ML libraries to save RAM and speed up Django startup
    import tensorflow as tf
    from tensorflow.keras.models import Sequential #type: ignore
    from tensorflow.keras.layers import LSTM, Dense, Dropout  # type: ignore
    from tensorflow.keras.callbacks import EarlyStopping  # type: ignore

    try:
        gpu_devices = tf.config.experimental.list_physical_devices('GPU')
        if gpu_devices:
            tf.config.experimental.set_memory_growth(gpu_devices[0], True)
    except Exception as e:
        print("GPU setup skipped:", e)

    # Scale the data
    scaler = MinMaxScaler(feature_range=(0, 1))
    data_scaled = scaler.fit_transform(data.reshape(-1, 1)).astype('float32')

    # Prepare data for LSTM
    X, y = prepare_data(data_scaled, look_back)

    # Check if data length is sufficient
    if len(X) == 0:
        average_prediction = np.mean(data)
        return average_prediction

    X = X.reshape(X.shape[0], X.shape[1], 1) 

    # Split data into training and test sets
    train_size = int(len(X) * 0.8)
    X_train, X_test = X[:train_size], X[train_size:]
    y_train, y_test = y[:train_size], y[train_size:]

    # Using tf.data for faster data pipeline
    train_data = tf.data.Dataset.from_tensor_slices((X_train, y_train)).batch(batch_size).repeat().prefetch(tf.data.AUTOTUNE)
    test_data = tf.data.Dataset.from_tensor_slices((X_test, y_test)).batch(batch_size).prefetch(tf.data.AUTOTUNE)

    # Define the LSTM model
    model = Sequential([
        tf.keras.Input(shape=(look_back, 1)),
        LSTM(units=32, return_sequences=True),
        Dropout(0.2),
        LSTM(units=16),
        Dropout(0.2),
        Dense(1)
    ])

    # Compile and train the model
    model.compile(optimizer='adam', loss='mean_squared_error')

    # Early stopping to reduce overfitting and speed up training
    early_stop = EarlyStopping(monitor='val_loss', patience=5, restore_best_weights=True)

    # Calculate steps per epoch
    steps_per_epoch = max(1, len(X_train) // batch_size)
    validation_steps = max(1, len(X_test) // batch_size)

    model.fit(
        train_data,
        validation_data=test_data,
        steps_per_epoch=steps_per_epoch,
        validation_steps=validation_steps,
        epochs=epochs,
        callbacks=[early_stop],
        verbose=1
    )

    # Predict the next n days
    last_sequence = data_scaled[-look_back:]
    for _ in range(next_days):
        last_sequence = last_sequence.reshape(1, look_back, 1)
        next_value = model.predict(last_sequence, verbose=0)
        next_value = next_value.reshape((1, 1, 1))
        last_sequence = np.concatenate([last_sequence[:, 1:, :], next_value], axis=1)

    # Get the last predicted value and inverse transform to original scale
    final_prediction = scaler.inverse_transform(next_value[0, 0].reshape(-1, 1))[0][0]
    return final_prediction

def run_prediction_thread(session_key, prediction_type, products_list, look_back, next_days, sales_column):
    predictions = {}
    true_all = []
    pred_all = []

    cancel_cache_key = f"cancel_predict_{session_key}"
    status_cache_key = f"prediction_status_{session_key}"

    # Iterate over each product and predict stock needed
    for product in products_list:
        # Check for cancellation signal
        if cache.get(cancel_cache_key):
            print(f"\n🚫 Prediction forcefully cancelled at product: {product}")
            cache.set(status_cache_key, 'cancelled', timeout=3600)
            return
            
        df = get_sales_dataframe()
        # Get sales data for the product
        product_data = df[df['product_name'] == product][sales_column].values

        # Check if sufficient data is available
        available_data_len = len(product_data)
        adjusted_look_back = min(look_back, available_data_len)

        if available_data_len > 0:
            if available_data_len < look_back:
                average_prediction = np.mean(product_data)
                predictions[product] = round(average_prediction)
                 # Store for accuracy
                true_all.append(product_data[-1])
                pred_all.append(average_prediction)
            else:
                pred_value = train_predict_lstm(product_data, look_back=adjusted_look_back, next_days=next_days)
                predictions[product] = round(pred_value)
                 # Store for accuracy
                true_all.append(product_data[-1])
                pred_all.append(pred_value)
        else:
            predictions[product] = round(np.mean(df[sales_column].values))

    if true_all and pred_all:
        overall_r2 = r2_score(true_all, pred_all)
        print(f"\n🔍 Final Overall R² Score across all products: {overall_r2:.4f}")
       
    # Save predictions to session
    session = SessionStore(session_key=session_key)
    session['predictions'] = predictions
    session['prediction_type'] = prediction_type
    session.save()
    
    # Update status to completed
    cache.set(status_cache_key, 'completed', timeout=3600)

def predict_stock(request):
    predictions = {}
    prediction_type = ''

    # Only run prediction or update if the request method is POST
    if request.method == 'POST':
        # Check if the "Add Stock to Database" button is clicked
        if 'add_stock' in request.POST:
            # Get the predictions from the session 
            predictions = request.session.get('predictions', {})

            batch = db.batch()
            all_products = db.collection('products').stream()
            product_dict = {p.to_dict().get('product_name'): p.id for p in all_products}

            for product, prediction in predictions.items():
                if product in product_dict:
                    doc_id = product_dict[product]
                    doc_ref = db.collection('products').document(doc_id)
                    batch.update(doc_ref, {'current_stock_level': prediction})

            try:
                batch.commit()
                print("Successfully updated all stock levels in batch")
            except Exception as e:
                print(f"Error executing batch update: {e}")

            messages.success(request, "Stocks updated")
            return redirect('stock_prediction')

        prediction_type = request.POST.get('prediction_type', '').strip().lower()

        if prediction_type == 'week':
            sales_column = 'sales_last_week'
            look_back = 7
            next_days = 7
        elif prediction_type == 'month':
            sales_column = 'sales_last_month'
            look_back = 30
            next_days = 30
        else:
            sales_column = 'sales_last_week'
            look_back = 7
            next_days = 1

        df = get_sales_dataframe()
        products_list = df['product_name'].unique().tolist()
        
        session_key = request.session.session_key
        if not session_key:
            request.session.create()
            session_key = request.session.session_key

        cancel_cache_key = f"cancel_predict_{session_key}"
        status_cache_key = f"prediction_status_{session_key}"

        cache.delete(cancel_cache_key)
        cache.set(status_cache_key, 'running', timeout=3600)

        thread = threading.Thread(
            target=run_prediction_thread, 
            args=(session_key, prediction_type, products_list, look_back, next_days, sales_column)
        )
        thread.start()

        return JsonResponse({'status': 'started'})
    
    # Retrieve predictions from session if available
    predictions = request.session.get('predictions', {})
    prediction_type = request.session.get('prediction_type', 'No Selection')

    return render(request, 'dashboard/stock_prediction.html', {
        'predictions': predictions, 
        'prediction_type': prediction_type,
    })

def reset_prediction_cache(request):
    # Clear the session cache data
    request.session.pop('predictions', None)
    request.session.pop('prediction_type', None)

    # Redirect back to the stock prediction page
    return redirect('stock_prediction') 

def cancel_prediction(request):
    if request.method == 'POST':
        cancel_cache_key = f"cancel_predict_{request.session.session_key}"
        cache.set(cancel_cache_key, True, timeout=60)
        return JsonResponse({'status': 'cancelled'})
    return JsonResponse({'status': 'invalid request'}, status=400)

def prediction_status(request):
    session_key = request.session.session_key
    if not session_key:
        return JsonResponse({'status': 'none'})
    status = cache.get(f"prediction_status_{session_key}", 'none')
    return JsonResponse({'status': status})

def admin_login(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        # Firebase Authentication using REST API for verifying email and password
        firebase_api_key = settings.FIREBASE_APIKEY
        firebase_auth_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={firebase_api_key}"
        
        payload = {
            "email": email,
            "password": password,
            "returnSecureToken": True
        }
        
        try:
            # Send POST request to Firebase Authentication REST API
            response = requests.post(firebase_auth_url, json=payload)
            response_data = response.json()

            # Check if authentication was successful
            if response.status_code == 200:
                # Authentication successful
                request.session['uid'] = response_data['localId']  # Store user ID in session
                return redirect('dashboard_overview')
            else:
                # Authentication failed
                error_message = response_data.get('error', {}).get('message', 'Invalid email or password.')
                messages.error(request, error_message)
        except requests.exceptions.RequestException as e:
            print(e)
            messages.error(request, 'An error occurred while trying to authenticate.')

    return render(request, 'dashboard/admin_login.html')

    
# Admin dashboard view
def dashboard_view(request):
    # Check if user is authenticated
    if 'uid' in request.session:
        return render(request, 'dashboard/dashboard_overview.html')
    else:
        return redirect('admin_login')

# Admin logout view
def admin_logout(request):
    logout(request)
    if 'uid' in request.session:
        del request.session['uid']
    return redirect('admin_login')

def dashboard_overview(request):
    # Retrieve the cached data and timestamp from the session
    cached_data = request.session.get('dashboard_cache')
    cache_time = request.session.get('dashboard_cache_time')

    # Check if cached data exists and is less than 10 minutes old
    if cached_data and cache_time and (time.time() - cache_time < 1800):  # 600 seconds = 10 minutes
        context = cached_data
    else:
        # Get product data
        product_list = get_products_list()

        # Get sales data
        sales_list = get_sales_list()

        # Aggregate sales data for performance metrics
        total_sales = sum(sale['total_price'] for sale in sales_list)
        total_orders = len(sales_list)
        total_customers = len(set(sale['customer_key'] for sale in sales_list))

        # Handle division by zero in monthly_growth calculation
        last_3_months_total = sum(sale.get('sales_last_3_months', 0) for sale in sales_list)
        last_month_total = sum(sale.get('sales_last_month', 0) for sale in sales_list)
        monthly_growth = round((last_month_total / last_3_months_total) * 100, 2) if last_3_months_total > 0 else 0

        # Calculate total revenue per sale
        for sale in sales_list:
            sale['total_revenue'] = round(sale.get('sales_last_month', 0) * sale.get('unit_price', 0), 2)

        # Prepare context
        context = {
            'total_sales': total_sales,
            'total_orders': total_orders,
            'total_customers': total_customers,
            'monthly_growth': monthly_growth,
            'products': product_list,
            'sales_data': sales_list,
            'top_selling_products': sorted(sales_list, key=lambda x: x.get('sales_last_month', 0), reverse=True)[:5],
        }

        # Store the fresh data and timestamp in the session
        request.session['dashboard_cache'] = context
        request.session['dashboard_cache_time'] = time.time()

    return render(request, 'dashboard/dashboard_overview.html', context)

def reset_dashboard_cache(request):
    # Clear the session cache data
    request.session.pop('dashboard_cache', None)
    request.session.pop('dashboard_cache_time', None)

    # Redirect back to the dashboard overview page
    return redirect('dashboard_overview') 

def stock_management(request):
    return render(request, 'dashboard/stock_management.html')

def reports_analytics(request):
    sales_cache_key = "sales_data_cache"
    sales_cache_expiry_key = "sales_data_cache_expiry"
    products_cache_key = "products_data_cache"
    refresh = request.GET.get("refresh") == "true"

    if refresh:
        cache.delete('sales_list')
        cache.delete('products_list')
        cache.delete('sales_dataframe')

    sales_data = get_sales_list()
    products_data = get_products_list()

    # **Calculate Key Metrics**
    total_sales = sum(float(data["total_price"]) for data in sales_data)
    total_units_sold = sum(int(data["order_quantity"]) for data in sales_data)
    avg_discount = sum(float(data["discount_percentage"]) for data in sales_data) / len(sales_data)

    # **Best-Selling Products (by Quantity)**
    best_selling_products = {}
    for data in sales_data:
        product = data["product_name"]
        best_selling_products[product] = best_selling_products.get(product, 0) + int(data["order_quantity"])
    
    best_selling_products = dict(sorted(best_selling_products.items(), key=lambda x: x[1], reverse=True)[:5])

    # **Top Revenue Products (by Total Price)**
    top_revenue_products = {}
    for data in sales_data:
        product = data["product_name"]
        top_revenue_products[product] = top_revenue_products.get(product, 0) + int(data["total_price"])

    top_revenue_products = dict(sorted(top_revenue_products.items(), key=lambda x: x[1], reverse=True)[:5])
    
    low_stock_products = sorted(
    [
        {
            "product_name": product["product_name"],
            "stock": int(product["current_stock_level"])
        }
        for product in products_data
        if "current_stock_level" in product and int(product["current_stock_level"]) < 50
    ],
    key=lambda x: x["stock"],
    reverse=True
)

    # **Sales Trends**
    sales_last_week = sum(int(data["sales_last_week"]) for data in sales_data)
    sales_last_month = sum(int(data["sales_last_month"]) for data in sales_data)
    sales_last_3_months = sum(int(data["sales_last_3_months"]) for data in sales_data)

    context = {
        "total_sales": total_sales,
        "total_units_sold": total_units_sold,
        "avg_discount": avg_discount,
        "best_selling_products": best_selling_products,
        "top_revenue_products": top_revenue_products,
        "low_stock_products": low_stock_products,
        "sales_last_week": sales_last_week,
        "sales_last_month": sales_last_month,
        "sales_last_3_months": sales_last_3_months,
    }

    return render(request, 'dashboard/reports_analytics.html', context)

def reset_reports_cache(request):
    # Clear cache keys
    cache.delete('sales_list')
    cache.delete('products_list')
    cache.delete('sales_dataframe')

    # Redirect back to reports analytics page
    return redirect('reports_analytics')



creds_json = os.getenv("GOOGLE_CREDENTIALS")
creds_dict = json.loads(creds_json)
SCOPES = ['https://www.googleapis.com/auth/firebase.messaging']
PROJECT_ID = 'homehub-b1065'

def get_access_token():
    credentials = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=SCOPES
    )
    credentials.refresh(Request())
    return credentials.token

def send_firebase_notification(title, body):
    access_token = get_access_token()

    url = f'https://fcm.googleapis.com/v1/projects/{PROJECT_ID}/messages:send'
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json; UTF-8',
    }

    message = {
        "message": {
            "topic": "all_users",
            "notification": {
                "title": title,
                "body": body
            }
        }
    }

    response = requests.post(url, headers=headers, json=message)
    print(f'FCM Notification sent. Status: {response.status_code}, Response: {response.text}')
def upload_to_github(file):
    # Extract settings
    token = settings.GITHUB_TOKEN
    repo = settings.GITHUB_REPO
    branch = settings.GITHUB_BRANCH
    filename = file.name
    upload_path = f'models/{filename}'

    # Read and encode file content
    file_content = file.read()
    content_encoded = base64.b64encode(file_content).decode('utf-8')

    # Prepare GitHub API endpoint
    url = f'https://api.github.com/repos/{repo}/contents/{upload_path}'
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
    }

    # 1. NEW: Check if the file already exists in the repo to fetch its SHA
    sha = None
    try:
        check_response = requests.get(f"{url}?ref={branch}", headers=headers)
        if check_response.status_code == 200:
            sha = check_response.json().get('sha')
    except Exception as e:
        print(f"Pre-check failed, proceeding as new file upload: {e}")

    data = {
        'message': f'Upload 3D model: {filename}',
        'branch': branch,
        'content': content_encoded,
    }

    # 2. NEW: If a SHA was found, append it to authorize an overwrite
    if sha:
        data['sha'] = sha

    # Make the PUT request to upload the file
    response = requests.put(url, headers=headers, json=data)

    if response.status_code in [200, 201]:
        username, repo_name = repo.split('/')
        
        # 3. IMPROVEMENT: Swapped hardcoded 'main' for the dynamic {branch} variable
        model_url = f'https://raw.githubusercontent.com/{username}/{repo_name}/{branch}/models/{filename}'
        return model_url
    else:
        # Optional: log or raise detailed error
        raise Exception(f"Failed to upload: {response.status_code} {response.text}")
        
# Add New Product View
def add_new_products(request):
    if request.method == 'POST':
        # Get form data
        product_name = request.POST.get('product_name', '').strip()
        category_name = request.POST.get('category_name', '').strip()
        subcategory = request.POST.get('subcategory', '').strip()
        current_stock_level = request.POST.get('current_stock_level', '0').strip()
        discount = request.POST.get('discount', '0').strip()
        price = request.POST.get('price', '0').strip()
        image_url = request.POST.get('image_url', '').strip()
        product_key = request.POST.get('product_key', '').strip()
        model_file = request.FILES.get('model_file')

        # Input validation...
        try:
            current_stock_level = int(current_stock_level)
        except ValueError:
            messages.error(request, "Current Stock Level must be an integer.")
            return redirect('add_new_products')

        try:
            discount = float(discount)
            if not (0 <= discount <= 1):
                messages.error(request, "Discount must be between 0 and 1.")
                return redirect('add_new_products')
        except ValueError:
            messages.error(request, "Discount must be a decimal between 0 and 1.")
            return redirect('add_new_products')

        try:
            price = int(price)
        except ValueError:
            messages.error(request, "Price must be an integer.")
            return redirect('add_new_products')

        if product_key.isdigit():
            product_key = int(product_key)

        # Handle 3D model upload to Google Drive
        model_url = ''
        if model_file:

            allowed_extensions = ['.glb', '.fbx', '.obj']
            ext = os.path.splitext(model_file.name)[1].lower()

            if ext not in allowed_extensions:
                messages.error(request, "Only .glb, .fbx, and .obj files are allowed for 3D model upload.")
                return redirect('add_new_products')
            
            try:
                model_url = upload_to_github(model_file)
            except Exception as e:
                messages.error(request, f"Error uploading model to Github: {str(e)}")
                return redirect('add_new_products')

        # Create product data dictionary
        product_data = {
            'product_name': product_name,
            'category_name': category_name,
            'subcategory': subcategory,
            'current_stock_level': current_stock_level,
            'discount': discount,
            'price': price,
            'image_url': image_url,
            'product_key': product_key,
            'model_url': model_url  # Store the model URL from Google Drive
        }

        # Add product to Firestore
        db.collection('products').add(product_data)

        #  Send push notification
        send_firebase_notification(
            title='New Product Added!',
            body=f'{product_name} is now available. Check it out!'
        )

        # Show success message
        messages.success(request, f'Product "{product_name}" added successfully!')
        return redirect('add_new_products')

    return render(request, 'dashboard/add_new_products.html')

# Search Product
def search_product(request):
    query = request.GET.get('query')
    print(query)
    if query:
        # Searching for the product in Firestore
        products_ref = db.collection('products')
        docs = products_ref.where('product_name', '==', query).stream()
        # print(docs)

        for doc in docs:
            product = doc.to_dict()
            product['id'] = doc.id
            return JsonResponse({'success': True, 'product': product})

    return JsonResponse({'success': False})


def product_suggestions(request):
    query = request.GET.get('term', '').lower()
    force_refresh = request.GET.get('refresh', 'false') == 'true'
    suggestions = []

    # Use a single cache key for all product names
    cache_key = 'all_product_suggestions'

    # If cache exists and refresh not requested, use from session
    if not force_refresh and cache_key in request.session:
        print("fetched from cache")
        all_product_names = request.session[cache_key]
    else:
        print("fetching from database")
        # Fetch all product names from Firestore
        all_product_names = []
        products_ref = db.collection('products')
        docs = products_ref.stream()
        for doc in docs:
            product = doc.to_dict()
            name = product.get('product_name', '')
            if name:
                all_product_names.append(name)

        # Cache the full list in session
        request.session[cache_key] = all_product_names
        request.session.modified = True

    # Now filter based on the current query
    if query:
        suggestions = [name for name in all_product_names if query in name.lower()]

    return JsonResponse(suggestions, safe=False)

def reset_product_suggestion_cache(request):
    # Clear cache keys
    request.session.pop("all_product_suggestions", None)
    return redirect('stock_management')

def update_stock(request):
    query = request.GET.get('query')
    updated_stock = request.GET.get('updated_stock')
    print(f"Query: {query}")
    print(f"Updated Stock: {updated_stock}")

    if query and updated_stock:
        products_ref = db.collection('products')
        docs = products_ref.where('product_name', '==', query).stream()

        for doc in docs:
            product_id = doc.id
            product_data = doc.to_dict()
            previous_stock = product_data.get('current_stock_level', 0)  # Get previous stock

            # Update Firestore with the new stock level only
            db.collection('products').document(product_id).update({
                'current_stock_level': int(updated_stock)
            })

            # Store the recent update in session or a temporary place
            if 'recent_updates' not in request.session:
                request.session['recent_updates'] = []
            
            # Store product name, previous and updated stock in session
            request.session['recent_updates'].insert(0, {
                'product_name': product_data.get('product_name'),
                'previous_stock_level': previous_stock,
                'current_stock_level': int(updated_stock)
            })
            
            # Keep only the last 10 updates
            request.session['recent_updates'] = request.session['recent_updates'][:10]

            request.session.modified = True  # Mark session as modified

            print("Stock Updated Successfully")
            return JsonResponse({'success': True})

    print("Stock Update Failed")
    return JsonResponse({'success': False})

def recent_updates(request):
    # Get recent updates from session
    recent_updates = request.session.get('recent_updates', [])

    # Format the response
    formatted_products = [
        {
            'product_name': product.get('product_name'),
            'previous_stock_level': product.get('previous_stock_level', 'N/A'),
            'current_stock_level': product.get('current_stock_level')
        }
        for product in recent_updates
    ]

    return JsonResponse({'success': True, 'recent_products': formatted_products})


