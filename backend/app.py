from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import jwt

app = Flask(__name__)
app.config['SECRET_KEY'] = 'love2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///loveswipe.db'
CORS(app)
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True)
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(200))
    age = db.Column(db.Integer, default=25)

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    from_user = db.Column(db.Integer)
    to_user = db.Column(db.Integer)

class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user1 = db.Column(db.Integer)
    user2 = db.Column(db.Integer)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer)
    from_user = db.Column(db.Integer)
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

def generate_token(user_id):
    return jwt.encode({'user_id': user_id, 'exp': datetime.utcnow() + timedelta(days=7)}, app.config['SECRET_KEY'])

def verify_token(token):
    try:
        return jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])['user_id']
    except:
        return None

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Email exists'}), 400
    user = User(username=data['username'], email=data['email'], password=data['password'], age=data.get('age', 25))
    db.session.add(user)
    db.session.commit()
    return jsonify({'success': True, 'token': generate_token(user.id), 'user_id': user.id})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(email=data['email']).first()
    if not user or user.password != data['password']:
        return jsonify({'error': 'Invalid credentials'}), 401
    return jsonify({'success': True, 'token': generate_token(user.id), 'user_id': user.id})

@app.route('/api/feed', methods=['GET'])
def get_feed():
    auth = request.headers.get('Authorization')
    if not auth:
        return jsonify({'error': 'Unauthorized'}), 401
    token = auth.split(' ')[1]
    current_id = verify_token(token)
    if not current_id:
        return jsonify({'error': 'Invalid token'}), 401
    liked = [l.to_user for l in Like.query.filter_by(from_user=current_id).all()]
    users = User.query.filter(User.id != current_id, User.id.notin_(liked)).limit(20).all()
    return jsonify([{'id': u.id, 'username': u.username, 'age': u.age} for u in users])

@app.route('/api/like', methods=['POST'])
def like():
    auth = request.headers.get('Authorization')
    token = auth.split(' ')[1]
    current_id = verify_token(token)
    data = request.json
    target = data['user_id']
    like = Like(from_user=current_id, to_user=target)
    db.session.add(like)
    db.session.commit()
    reverse = Like.query.filter_by(from_user=target, to_user=current_id).first()
    if reverse:
        match = Match(user1=min(current_id, target), user2=max(current_id, target))
        db.session.add(match)
        db.session.commit()
        return jsonify({'match': True})
    return jsonify({'match': False})

@app.route('/api/matches', methods=['GET'])
def get_matches():
    auth = request.headers.get('Authorization')
    token = auth.split(' ')[1]
    current_id = verify_token(token)
    matches = Match.query.filter((Match.user1 == current_id) | (Match.user2 == current_id)).all()
    result = []
    for m in matches:
        other = m.user2 if m.user1 == current_id else m.user1
        user = User.query.get(other)
        result.append({'id': m.id, 'user_id': user.id, 'username': user.username})
    return jsonify(result)

@app.route('/api/messages/<int:match_id>', methods=['GET'])
def get_messages(match_id):
    msgs = Message.query.filter_by(match_id=match_id).order_by(Message.created_at).all()
    return jsonify([{'id': m.id, 'from_user': m.from_user, 'message': m.message} for m in msgs])

@socketio.on('send_message')
def handle_message(data):
    msg = Message(match_id=data['match_id'], from_user=data['from_user'], message=data['message'])
    db.session.add(msg)
    db.session.commit()
    emit('new_message', data, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8001)
