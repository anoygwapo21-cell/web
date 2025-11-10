from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///events.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ------------------ DATABASE MODEL ------------------
class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    time = db.Column(db.String(10), nullable=False)
    description = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f'<Event {self.title}>'

# ------------------ ROUTES ------------------

# Landing page
@app.route('/')
def landing():
    return render_template('landing.html')

# Event dashboard
@app.route('/home')
def index():
    search_query = request.args.get('search', '').strip()
    if search_query:
        events = Event.query.filter(
            (Event.title.like(f"%{search_query}%")) |
            (Event.date.like(f"%{search_query}%"))
        ).order_by(Event.date).all()
    else:
        events = Event.query.order_by(Event.date).all()
    return render_template('index.html', events=events, search_query=search_query)

# Add Event
@app.route('/add', methods=['GET', 'POST'])
def add_event():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        date = request.form.get('date', '').strip()
        time = request.form.get('time', '').strip()
        description = request.form.get('description', '').strip()

        if not title or not date or not time:
            flash("Title, date, and time are required.", "error")
            return render_template('add.html')

        try:
            new_event = Event(title=title, date=date, time=time, description=description)
            db.session.add(new_event)
            db.session.commit()
            flash("Event added successfully!", "success")
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error adding event: {str(e)}", "error")
            return render_template('add.html')

    return render_template('add.html')

# Edit Event
@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_event(id):
    event = Event.query.get_or_404(id)
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        date = request.form.get('date', '').strip()
        time = request.form.get('time', '').strip()
        description = request.form.get('description', '').strip()

        if not title or not date or not time:
            flash("Title, date, and time are required.", "error")
            return render_template('edit.html', event=event)

        try:
            event.title = title
            event.date = date
            event.time = time
            event.description = description
            db.session.commit()
            flash("Event updated successfully!", "success")
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating event: {str(e)}", "error")
            return render_template('edit.html', event=event)

    return render_template('edit.html', event=event)

# Delete Event
@app.route('/delete/<int:id>')
def delete_event(id):
    try:
        event = Event.query.get_or_404(id)
        db.session.delete(event)
        db.session.commit()
        flash("Event deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting event: {str(e)}", "error")
    return redirect(url_for('index'))

# ------------------ RUN APP ------------------
if __name__ == '__main__':

    if not os.path.exists('events.db'):
        with app.app_context():
            db.create_all()
            print("Database created successfully!")

    app.run(debug=True)
