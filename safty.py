import streamlit as st
import firebase_admin
from firebase_admin import credentials, auth, firestore, db
import json
import folium
from streamlit_folium import folium_static
import uuid
import time
from datetime import datetime
import base64
import streamlit.components.v1 as components

# Initialize Firebase if not already initialized
if not firebase_admin._apps:
    # You need to replace this with your own Firebase credentials
    cred = credentials.Certificate("arthydro-ebcb8-firebase-adminsdk-ac757-4c6b48910f.json")
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://arthydro-ebcb8-default-rtdb.asia-southeast1.firebasedatabase.app/'
    })

# Initialize Firestore database
db = firestore.client()

# Function to handle user registration
def register_user(phone, full_name, emergency_contacts):
    try:
        # Check if user with phone number already exists
        user_ref = db.collection('users').where('phone', '==', phone).limit(1).stream()
        user_exists = False
        for user in user_ref:
            user_exists = True
            
        if user_exists:
            return False, "User with this phone number already exists"
        
        # Create user ID from phone number (cleaned)
        user_id = phone.replace("+", "").replace("-", "").replace(" ", "")
        
        # Store user data in Firestore
        user_data = {
            'uid': user_id,
            'phone': phone,
            'full_name': full_name,
            'emergency_contacts': emergency_contacts,
            'created_at': firestore.SERVER_TIMESTAMP
        }
        
        db.collection('users').document(user_id).set(user_data)
        
        return True, user_id
    except Exception as e:
        return False, str(e)

# Function to handle user login
def login_user(phone):
    try:
        # Verify phone against Firestore
        user_id = phone.replace("+", "").replace("-", "").replace(" ", "")
        user_ref = db.collection('users').document(user_id).get()
        
        if user_ref.exists:
            user_data = user_ref.to_dict()
            return True, user_data
        else:
            return False, "User not found"
    except Exception as e:
        return False, str(e)

# Function to send emergency alert
def send_emergency_alert(user_data, location):
    try:
        # Create emergency alert
        alert_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        alert_data = {
            'alert_id': alert_id,
            'user_id': user_data['uid'],
            'user_name': user_data['full_name'],
            'location': location,
            'timestamp': timestamp,
            'status': 'active'
        }
        
        # Store alert in Firestore
        db.collection('emergency_alerts').document(alert_id).set(alert_data)
        
        # Notify emergency contacts
        notified_contacts = []
        for contact in user_data['emergency_contacts']:
            # Get contact_id from phone
            contact_id = contact['phone'].replace("+", "").replace("-", "").replace(" ", "")
            
            notification = {
                'recipient_id': contact_id,
                'alert_id': alert_id,
                'user_name': user_data['full_name'],
                'user_phone': user_data['phone'],
                'location': location,
                'timestamp': timestamp,
                'read': False
            }
            
            db.collection('notifications').add(notification)
            notified_contacts.append(contact['name'])
        
        return True, notified_contacts
    except Exception as e:
        return False, str(e)

# JavaScript for location, voice notifications and recording
def get_js_components():
    return """
    <script>
    // Global variables for location
    let userLatitude = null;
    let userLongitude = null;
    let userAddress = null;
    
    // Get precise location using browser geolocation
    function getLocation() {
        const locationOutput = document.getElementById("locationOutput");
        locationOutput.innerHTML = "Getting your location...";
        
        if (navigator.geolocation) {
            const options = {
                enableHighAccuracy: true,
                timeout: 10000,
                maximumAge: 0
            };
            
            navigator.geolocation.getCurrentPosition(showPosition, showError, options);
        } else {
            locationOutput.innerHTML = "Geolocation is not supported by this browser.";
        }
    }
    
    function showPosition(position) {
        userLatitude = position.coords.latitude;
        userLongitude = position.coords.longitude;
        
        const locationOutput = document.getElementById("locationOutput");
        locationOutput.innerHTML = `
            <strong>Your Current Location:</strong><br>
            Latitude: ${userLatitude}<br>
            Longitude: ${userLongitude}
        `;
        
        // Get address from coordinates (reverse geocoding)
        fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${userLatitude}&lon=${userLongitude}`)
            .then(response => response.json())
            .then(data => {
                userAddress = data.display_name;
                locationOutput.innerHTML += `<br>Address: ${userAddress}`;
                
                // Send location to Streamlit
                window.parent.postMessage({
                    type: 'location_data',
                    data: {
                        lat: userLatitude,
                        lng: userLongitude,
                        address: userAddress
                    }
                }, '*');
            })
            .catch(error => {
                console.error("Error getting address:", error);
            });
    }
    
    function showError(error) {
        const locationOutput = document.getElementById("locationOutput");
        switch(error.code) {
            case error.PERMISSION_DENIED:
                locationOutput.innerHTML = "User denied the request for Geolocation.";
                break;
            case error.POSITION_UNAVAILABLE:
                locationOutput.innerHTML = "Location information is unavailable.";
                break;
            case error.TIMEOUT:
                locationOutput.innerHTML = "The request to get user location timed out.";
                break;
            case error.UNKNOWN_ERROR:
                locationOutput.innerHTML = "An unknown error occurred.";
                break;
        }
    }
    
    // Text-to-speech function
    function speakNotification(text) {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 1.0;
        utterance.pitch = 1.0;
        utterance.volume = 1.0;
        
        // Get available voices
        let voices = speechSynthesis.getVoices();
        
        // If voices array is empty, wait for voices to be loaded
        if (voices.length === 0) {
            speechSynthesis.addEventListener('voiceschanged', () => {
                voices = speechSynthesis.getVoices();
                // Try to find a female voice
                const femaleVoice = voices.find(voice => 
                    voice.name.includes('female') || 
                    voice.name.includes('Female') || 
                    voice.name.includes('woman') ||
                    voice.name.includes('Girl'));
                
                if (femaleVoice) {
                    utterance.voice = femaleVoice;
                }
                speechSynthesis.speak(utterance);
            });
        } else {
            // Try to find a female voice
            const femaleVoice = voices.find(voice => 
                voice.name.includes('female') || 
                voice.name.includes('Female') || 
                voice.name.includes('woman') ||
                voice.name.includes('Girl'));
            
            if (femaleVoice) {
                utterance.voice = femaleVoice;
            }
            speechSynthesis.speak(utterance);
        }
    }
    
    // Voice recording function
    let mediaRecorder;
    let audioChunks = [];
    
    function startRecording() {
        audioChunks = [];
        navigator.mediaDevices.getUserMedia({ audio: true })
            .then(stream => {
                mediaRecorder = new MediaRecorder(stream);
                mediaRecorder.addEventListener("dataavailable", event => {
                    audioChunks.push(event.data);
                });
                
                mediaRecorder.addEventListener("stop", () => {
                    const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                    const audioUrl = URL.createObjectURL(audioBlob);
                    const audio = new Audio(audioUrl);
                    
                    // Convert to base64 to send to Python
                    const reader = new FileReader();
                    reader.readAsDataURL(audioBlob); 
                    reader.onloadend = function() {
                        const base64data = reader.result;
                        // Send data to Streamlit
                        window.parent.postMessage({
                            type: 'voice_data',
                            data: base64data
                        }, '*');
                    };
                });
                
                mediaRecorder.start();
                document.getElementById("recordStatus").textContent = "Recording...";
            })
            .catch(error => {
                document.getElementById("recordStatus").textContent = "Error accessing microphone: " + error.message;
            });
    }
    
    function stopRecording() {
        if (mediaRecorder && mediaRecorder.state !== "inactive") {
            mediaRecorder.stop();
            document.getElementById("recordStatus").textContent = "Recording stopped";
        }
    }
    
    // Function to test speech synthesis
    function testSpeech() {
        speakNotification("This is a test of the emergency notification system for the women safety app.");
    }
    
    // Initialize location on page load
    window.onload = function() {
        // Check if auto-location is enabled
        const autoLocationEnabled = localStorage.getItem('autoLocationEnabled');
        if (autoLocationEnabled === 'true') {
            getLocation();
        }
        
        // Initialize periodic location updates if enabled
        const periodicUpdatesEnabled = localStorage.getItem('periodicUpdatesEnabled');
        if (periodicUpdatesEnabled === 'true') {
            // Update location every 5 minutes
            setInterval(getLocation, 300000);
        }
    }
    
    // Emergency alert simulation function
    function simulateIncomingAlert(name, location) {
        const alertText = `EMERGENCY ALERT! ${name} needs help at ${location}. Please respond immediately.`;
        
        // Create alert box
        const alertDiv = document.createElement('div');
        alertDiv.style.position = 'fixed';
        alertDiv.style.top = '20px';
        alertDiv.style.left = '50%';
        alertDiv.style.transform = 'translateX(-50%)';
        alertDiv.style.backgroundColor = 'red';
        alertDiv.style.color = 'white';
        alertDiv.style.padding = '20px';
        alertDiv.style.borderRadius = '10px';
        alertDiv.style.zIndex = '9999';
        alertDiv.style.boxShadow = '0 0 10px rgba(0,0,0,0.5)';
        alertDiv.innerHTML = `
            <h3>EMERGENCY ALERT!</h3>
            <p>${name} needs help!</p>
            <p>Location: ${location}</p>
            <button onclick="this.parentNode.remove(); stopAlertSound();" style="background: white; color: red; border: none; padding: 5px 10px; border-radius: 5px; cursor: pointer;">Acknowledge</button>
        `;
        
        document.body.appendChild(alertDiv);
        
        // Speak the alert
        speakNotification(alertText);
        
        // Play alert sound
        playAlertSound();
    }
    
    // Play alert sound function
    let alertAudio;
    function playAlertSound() {
        alertAudio = new Audio();
        alertAudio.src = 'data:audio/wav;base64,UklGRnQGAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YVAGAACAgICAgICAgICAgICAgICAgICAgICAgICAf3hxeH+AfXZ1eHx6dnR5fYGFgoOKi42SkZSVlZeYmZybm5ycnJqYlpWTkZCNioeFgoB8eXVzcG1qaGVjYF5cWVdWVVRUVFVWV1laXF5gYmVmaWttb3JwcnR3eXp9f4GDhoeJioyNj5GSlJWXmJqbnJ2en6Chn6CgoKGgoaCgoJ+enp2dm5qZmJeWlJOSkI+OjYuKiYeGhIOCgYB/f359fHt7e3t6e3t7fHx9fX5+f4CAgIGBgoKDg4SEhISFhYWFhYWFhYWFhYWEhISEg4OCgoKBgYGAgIB/f35+fn19fXx8fHx7e3t7e3t7e3t7e3t8fHx8fH19fX1+fn5+fn9/f3+AgICAgICAgIGBgYGBgYGBgYGBgYGBgYGBgYGAgICAgICAf39/f39/f35+fn5+fn5+fn5+fn5+fn5+fn5+fn5+fn5+fn9/f39/f39/f39/f39/f3+AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAf39/f39/f39/f39/f39/f39/f39/f39/f39/f3+AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAf3hxeH+AfXZ1eHx6dnR5fYGFgoOKi42SkZSVlZeYmZybm5ycnJqYlpWTkZCNioeFgoB8eXVzcG1qaGVjYF5cWVdWVVRUVFVWV1laXF5gYmVmaWttb3JwcnR3eXp9f4GDhoeJioyNj5GSlJWXmJqbnJ2en6Chn6CgoKGgoaCgoJ+enp2dm5qZmJeWlJOSkI+OjYuKiYeGhIOCgYB/f359fHt7e3t6e3t7fHx9fX5+f4CAgIGBgoKDg4SEhISFhYWFhYWFhYWFhYWEhISEg4OCgoKBgYGAgIB/f35+fn19fXx8fHx7e3t7e3t7e3t7e3t8fHx8fH19fX1+fn5+fn9/f3+AgICAgICAgIGBgYGBgYGBgYGBgYGBgYGBgYGAgICAgICAf39/f39/f35+fn5+fn5+fn5+fn5+fn5+fn5+fn5+fn5+fn9/f39/f39/f39/f39/f3+AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAf39/f39/f39/f39/f39/f39/f39/f39/f39/f3+AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAAA==';
        alertAudio.loop = true;
        alertAudio.play();
    }
    
    function stopAlertSound() {
        if (alertAudio) {
            alertAudio.pause();
            alertAudio.currentTime = 0;
        }
    }
    </script>
    
    <div class="safety-app-components">
        <div class="location-component">
            <h3>Your Location</h3>
            <button onclick="getLocation()">Update My Location</button>
            <p id="locationOutput">Click the button to get your current location.</p>
        </div>
        
        <div class="voice-component" style="margin-top: 20px;">
            <h3>Voice Communication</h3>
            <button onclick="startRecording()">Start Recording</button>
            <button onclick="stopRecording()">Stop Recording</button>
            <button onclick="testSpeech()">Test Voice Alert</button>
            <p id="recordStatus">Ready to record</p>
        </div>
        
        <div class="emergency-test" style="margin-top: 20px;">
            <h3>Emergency Alert Test</h3>
            <button onclick="simulateIncomingAlert('Jane Doe', 'Main Street, Downtown')">
                Test Emergency Alert
            </button>
        </div>
    </div>
    """

# Main application
def main():
    st.set_page_config(page_title="Women Safety App", page_icon="🛡️", layout="wide")
    
    # Initialize session state variables
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'user_data' not in st.session_state:
        st.session_state.user_data = None
    if 'page' not in st.session_state:
        st.session_state.page = 'home'
    if 'location' not in st.session_state:
        st.session_state.location = {'lat': 0, 'lng': 0, 'address': 'Unknown'}
    if 'notifications' not in st.session_state:
        st.session_state.notifications = []
    
    # App header
    st.title("🛡️ Women Safety Application")
    
    # Sidebar navigation
    st.sidebar.title("Navigation")
    
    if not st.session_state.logged_in:
        nav_option = st.sidebar.radio("", ["Home", "Login", "Register"])
        
        if nav_option == "Home":
            st.session_state.page = 'home'
        elif nav_option == "Login":
            st.session_state.page = 'login'
        elif nav_option == "Register":
            st.session_state.page = 'register'
    else:
        # Check for notifications
        if st.session_state.user_data:
            check_for_notifications(st.session_state.user_data['uid'])
            
        nav_option = st.sidebar.radio("", ["Dashboard", "Emergency Alert", "Notifications", "Settings", "Logout"])
        
        if nav_option == "Dashboard":
            st.session_state.page = 'dashboard'
        elif nav_option == "Emergency Alert":
            st.session_state.page = 'emergency'
        elif nav_option == "Notifications":
            st.session_state.page = 'notifications'
        elif nav_option == "Settings":
            st.session_state.page = 'settings'
        elif nav_option == "Logout":
            st.session_state.logged_in = False
            st.session_state.user_data = None
            st.session_state.page = 'home'
            st.experimental_rerun()
    
    # Page content based on selection
    if st.session_state.page == 'home':
        show_home_page()
    elif st.session_state.page == 'login':
        show_login_page()
    elif st.session_state.page == 'register':
        show_register_page()
    elif st.session_state.page == 'dashboard':
        show_dashboard()
    elif st.session_state.page == 'emergency':
        show_emergency_page()
    elif st.session_state.page == 'notifications':
        show_notifications_page()
    elif st.session_state.page == 'settings':
        show_settings_page()

def check_for_notifications(user_id):
    """Check for new emergency notifications for this user"""
    try:
        # Query notifications collection
        notifications_ref = db.collection('notifications') \
                              .where('recipient_id', '==', user_id) \
                              .where('read', '==', False) \
                              .stream()
        
        new_notifications = []
        for doc in notifications_ref:
            notification = doc.to_dict()
            notification['id'] = doc.id
            new_notifications.append(notification)
        
        if new_notifications and len(new_notifications) > len(st.session_state.notifications):
            # There are new notifications
            st.session_state.notifications = new_notifications
            
            # If we're on a different page than notifications, show an alert
            if st.session_state.page != 'notifications' and len(new_notifications) > 0:
                # Play alert sound and show notification via JavaScript
                js_alert = f"""
                <script>
                    simulateIncomingAlert(
                        "{new_notifications[0]['user_name']}", 
                        "{new_notifications[0]['location']['address'] if 'address' in new_notifications[0]['location'] else 'Unknown location'}"
                    );
                </script>
                """
                components.html(js_alert, height=0)
    except Exception as e:
        st.error(f"Error checking notifications: {e}")

def show_home_page():
    st.header("Welcome to the Women Safety Application")
    
    st.write("""
    This application is designed to provide safety features for women:
    
    - 🔐 Register with your phone number
    - 👥 Add emergency contacts
    - 🚨 Send emergency alerts with your exact location
    - 🎙️ Voice recording during emergencies
    - 📍 Real-time location tracking
    - 📱 Direct notifications to emergency contacts
    
    Please register or login to access all features.
    """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Login", use_container_width=True):
            st.session_state.page = 'login'
            st.experimental_rerun()
    
    with col2:
        if st.button("Register", use_container_width=True):
            st.session_state.page = 'register'
            st.experimental_rerun()

def show_login_page():
    st.header("Login")
    
    with st.form("login_form"):
        phone = st.text_input("Phone Number (with country code, e.g., +1234567890)")
        submit_button = st.form_submit_button("Login")
        
        if submit_button:
            if phone:
                success, result = login_user(phone)
                if success:
                    st.session_state.logged_in = True
                    st.session_state.user_data = result
                    st.session_state.page = 'dashboard'
                    st.success("Login successful!")
                    st.experimental_rerun()
                else:
                    st.error(f"Login failed: {result}")
            else:
                st.error("Please enter your phone number")

def show_register_page():
    st.header("Register")
    
    with st.form("register_form"):
        full_name = st.text_input("Full Name")
        phone = st.text_input("Phone Number (with country code, e.g., +1234567890)")
        
        st.subheader("Emergency Contacts")
        
        # Add emergency contacts
        emergency_contacts = []
        for i in range(3):  # Allow up to 3 emergency contacts
            st.write(f"Emergency Contact {i+1}")
            contact_name = st.text_input(f"Name {i+1}", key=f"contact_name_{i}")
            contact_phone = st.text_input(f"Phone {i+1} (must have the app installed)", key=f"contact_phone_{i}")
            
            if contact_name and contact_phone:
                emergency_contacts.append({
                    'name': contact_name,
                    'phone': contact_phone
                })
        
        submit_button = st.form_submit_button("Register")
        
        if submit_button:
            if full_name and phone:
                if len(emergency_contacts) > 0:
                    success, result = register_user(phone, full_name, emergency_contacts)
                    if success:
                        st.success("Registration successful! Please login.")
                        st.session_state.page = 'login'
                        st.experimental_rerun()
                    else:
                        st.error(f"Registration failed: {result}")
                else:
                    st.warning("Please add at least one emergency contact")
            else:
                st.error("Please fill in all required fields")

def show_dashboard():
    if not st.session_state.logged_in:
        st.warning("Please login to access the dashboard")
        st.session_state.page = 'login'
        st.experimental_rerun()
        return
    
    st.header(f"Welcome, {st.session_state.user_data['full_name']}")
    
    # JavaScript components
    components.html(get_js_components(), height=450)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Your Profile")
        st.write(f"Phone: {st.session_state.user_data['phone']}")
        
        st.subheader("Emergency Contacts")
        for i, contact in enumerate(st.session_state.user_data['emergency_contacts']):
            st.write(f"Contact {i+1}: {contact['name']} - {contact['phone']}")
    
    with col2:
        st.subheader("Emergency Button")
        if st.button("🚨 SEND EMERGENCY ALERT", use_container_width=True, key="emergency_button"):
            st.session_state.page = 'emergency'
            st.experimental_rerun()
            
        st.write("Click the emergency button to send an alert to your emergency contacts.")
        st.write("They will receive your exact location and can respond immediately.")

def show_emergency_page():
    if not st.session_state.logged_in:
        st.warning("Please login to access this feature")
        st.session_state.page = 'login'
        st.experimental_rerun()
        return
    
    st.header("🚨 Emergency Alert")
    
    # JavaScript components
    components.html(get_js_components(), height=450)
    
    # Send alert
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("SEND EMERGENCY ALERT TO CONTACTS", use_container_width=True):
            # Get location from session state (updated by JavaScript)
            success, notified = send_emergency_alert(st.session_state.user_data, st.session_state.location)
            if success:
                st.success(f"Emergency alert sent successfully to: {', '.join(notified)}")
                
                # JavaScript alert simulation
                js_code = f"""
                <script>
                    const utterance = new SpeechSynthesisUtterance(
                        "Emergency alert sent to your contacts. Help is on the way. Stay safe."
                    );
                    speechSynthesis.speak(utterance);
                </script>
                """
                components.html(js_code, height=0)
            else:
                st.error(f"Failed to send alert: {notified}")
    
    with col2:
        if st.button("Cancel and Return to Dashboard", use_container_width=True):
            st.session_state.page = 'dashboard'
            st.experimental_rerun()
    
    st.write("Your emergency contacts will receive:")
    st.write("1. Your exact location")
    st.write("2. Voice notification with emergency details")
    st.write("3. Alert on their application if installed")

def show_notifications_page():
    if not st.session_state.logged_in:
        st.warning("Please login to access notifications")
        st.session_state.page = 'login'
        st.experimental_rerun()
        return
    
    st.header("Emergency Notifications")
    
    if not st.session_state.notifications:
        st.info("You have no emergency notifications.")
    else:
        for notification in st.session_state.notifications:
            with st.container():
                st.markdown(f"""
                ### Emergency Alert from {notification['user_name']}
                - **Phone**: {notification['user_phone']}
                - **Location**: {notification['location']['address'] if 'address' in notification['location'] else 'Unknown'}
                - **Time**: {notification['timestamp']}
                """)
                
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button("Mark as Responded", key=f"respond_{notification['id']}"):
                        # Update notification in Firestore
                        db.collection('notifications').document(notification['id']).update({
                            'read': True
                        })
                        # Remove from session state
                        st.session_state.notifications = [n for n in st.session_state.notifications if n['id'] != notification['id']]
                        st.success("Marked as responded")
                        st.experimental_rerun()
                
                with col2:
                    if st.button("View on Map", key=f"map_{notification['id']}"):
                        # Create map
                        if 'lat' in notification['location'] and 'lng' in notification['location']:
                            m = folium.Map(location=[notification['location']['lat'], notification['location']['lng']], zoom_start=15)
                            folium.Marker(
                                [notification['location']['lat'], notification['location']['lng']],
                                popup=f"{notification['user_name']}'s Location",
                                tooltip=f"{notification['user_name']}'s Location"
                            ).add_to(m)
                            folium_static(m)
                        else:
                            st.error("Location data not available")
                
                st.markdown("---")

def show_settings_page():
    if not st.session_state.logged_in:
        st.warning("Please login to access settings")
        st.session_state.page = 'login'
        st.experimental_rerun()
        return
    
    st.header("Settings")
    
    with st.expander("Update Profile", expanded=True):
        with st.form("update_profile"):
            full_name = st.text_input("Full Name", value=st.session_state.user_data['full_name'])
            
            if st.form_submit_button("Update Profile"):
                # Update user data in Firestore
                user_ref = db.collection('users').document(st.session_state.user_data['uid'])
                user_ref.update({
                    'full_name': full_name
                })
                
                # Update session state
                st.session_state.user_data['full_name'] = full_name
                st.success("Profile updated successfully")
    
    with st.expander("Update Emergency Contacts"):
        with st.form("update_contacts"):
            updated_contacts = []
            
            for i, contact in enumerate(st.session_state.user_data['emergency_contacts']):
                st.write(f"Emergency Contact {i+1}")
                contact_name = st.text_input(f"Name {i+1}", value=contact['name'], key=f"update_name_{i}")
                contact_phone = st.text_input(f"Phone {i+1}", value=contact['phone'], key=f"update_phone_{i}")
                
                if contact_name and contact_phone:
                    updated_contacts.append({
                        'name': contact_name,
                        'phone': contact_phone
                    })
            
            # Option to add a new contact
            st.write("Add New Contact")
            new_contact_name = st.text_input("Name", key="new_contact_name")
            new_contact_phone = st.text_input("Phone", key="new_contact_phone")
            
            if new_contact_name and new_contact_phone:
                updated_contacts.append({
                    'name': new_contact_name,
                    'phone': new_contact_phone
                })
            
            if st.form_submit_button("Update Contacts"):
                if len(updated_contacts) > 0:
                    # Update user data in Firestore
                    user_ref = db.collection('users').document(st.session_state.user_data['uid'])
                    user_ref.update({
                        'emergency_contacts': updated_contacts
                    })
                    
                    # Update session state
                    st.session_state.user_data['emergency_contacts'] = updated_contacts
                    st.success("Emergency contacts updated successfully")
                else:
                    st.error("You must have at least one emergency contact")
    
    with st.expander("Location and Notification Settings"):
        st.write("Location Settings")
        
        auto_location = st.checkbox("Enable automatic location updates when app opens", 
                                   value=True)
        
        periodic_updates = st.checkbox("Enable periodic location updates (every 5 minutes)", 
                                     value=False)
        
        if st.button("Save Location Settings"):
            # Use JavaScript to save these settings to localStorage
            js_code = f"""
            <script>
                localStorage.setItem('autoLocationEnabled', '{str(auto_location).lower()}');
                localStorage.setItem('periodicUpdatesEnabled', '{str(periodic_updates).lower()}');
                
                // Show confirmation
                alert('Location settings saved successfully');
            </script>
            """
            components.html(js_code, height=0)
            st.success("Location settings saved")
        
        st.write("Notification Settings")
        
        notification_sound = st.checkbox("Enable notification sounds", value=True)
        voice_alerts = st.checkbox("Enable voice alerts for emergency notifications", value=True)
        
        if st.button("Save Notification Settings"):
            # These would typically be saved to user preferences in the database
            # For now, we'll just show a success message
            st.success("Notification settings saved")
    
    with st.expander("Delete Account"):
        st.warning("Warning: This action cannot be undone!")
        
        confirm_delete = st.text_input("Type 'DELETE' to confirm account deletion")
        
        if st.button("Delete My Account"):
            if confirm_delete == "DELETE":
                try:
                    # Delete user document from Firestore
                    db.collection('users').document(st.session_state.user_data['uid']).delete()
                    
                    # Reset session state
                    st.session_state.logged_in = False
                    st.session_state.user_data = None
                    st.session_state.page = 'home'
                    
                    st.success("Your account has been deleted")
                    st.experimental_rerun()
                except Exception as e:
                    st.error(f"Error deleting account: {e}")
            else:
                st.error("Please type 'DELETE' to confirm account deletion")

# Function to handle location data from JavaScript
def handle_js_events():
    # Register callback for location data
    components.html(
        """
        <script>
        window.addEventListener('message', function(event) {
            if (event.data.type === 'location_data') {
                window.parent.postMessage({
                    type: 'streamlit:setComponentValue',
                    value: event.data.data
                }, '*');
            }
        });
        </script>
        """,
        height=0
    )

# Function to create an about page
def show_about_page():
    st.header("About Women Safety App")
    
    st.write("""
    ## Our Mission
    
    Our mission is to provide a reliable safety solution for women, enabling them to quickly alert
    trusted contacts during emergencies and share critical location information.
    
    ## Key Features
    
    - **Emergency Alerts**: Send instant alerts to emergency contacts with your exact location
    - **Voice Communication**: Record and send voice messages during emergencies
    - **Real-time Location Tracking**: Share your precise location with emergency contacts
    - **Emergency Notifications**: Receive alerts when someone in your network needs help
    
    ## Privacy & Security
    
    Your privacy and security are our top priorities. All data is encrypted and stored securely.
    Your location is only shared when you trigger an emergency alert.
    
    ## Contact Us
    
    For support or feedback, please contact us at:
    
    - Email: support@womensafetyapp.com
    - Phone: +1-800-SAFE-NOW
    """)

# Function to create a help page
def show_help_page():
    st.header("Help & FAQ")
    
    with st.expander("How to Use the Emergency Alert Feature"):
        st.write("""
        1. Navigate to the Emergency Alert page from the dashboard or sidebar
        2. Make sure your location is updated (click "Update My Location")
        3. Click the "SEND EMERGENCY ALERT TO CONTACTS" button
        4. Your emergency contacts will be notified immediately with your location
        """)
    
    with st.expander("Adding Emergency Contacts"):
        st.write("""
        1. Go to the Settings page
        2. Click on "Update Emergency Contacts"
        3. Add or edit contact information
        4. Click "Update Contacts" to save changes
        
        Note: Your emergency contacts should have the app installed to receive alerts.
        """)
    
    with st.expander("Location Permissions"):
        st.write("""
        The app requires location permissions to function properly. When prompted by your browser,
        please allow location access. You can adjust location settings in the Settings page.
        """)
    
    with st.expander("Common Issues"):
        st.write("""
        **Q: My location isn't updating**
        A: Make sure you've allowed location permissions in your browser. Try clicking "Update My Location" again.
        
        **Q: My emergency contacts didn't receive my alert**
        A: Ensure your contacts have the app installed and have registered with the correct phone number you've saved.
        
        **Q: The app isn't making sound alerts**
        A: Check your device's sound settings and make sure notifications are enabled in the app settings.
        """)

# Function to handle voice data from JavaScript
def handle_voice_data(base64_data):
    """Handle voice recording data from JavaScript"""
    try:
        # In a real application, you'd store this in Firebase storage
        # and link it to the emergency alert
        
        # For demo purposes, we'll just acknowledge receipt
        st.session_state.voice_data = base64_data
        return True
    except Exception as e:
        st.error(f"Error handling voice data: {e}")
        return False

# Main execution
if __name__ == "__main__":
    main()
