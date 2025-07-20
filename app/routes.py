from flask import Blueprint, render_template, request, redirect, url_for, session
from .models import Product, Order, OrderItem
from . import db
from flask_wtf import FlaskForm
from wtforms import StringField, EmailField, SubmitField, IntegerField, HiddenField
from wtforms.validators import DataRequired, Email, Length, NumberRange
from flask_wtf.csrf import generate_csrf

bp = Blueprint('main', __name__)

class CheckoutForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(max=100)])
    email = EmailField('Email', validators=[DataRequired(), Email(), Length(max=100)])
    address = StringField('Address', validators=[DataRequired(), Length(max=255)])
    phone = StringField('Phone', validators=[DataRequired(), Length(max=20)])
    submit = SubmitField('Place Order')

class AddToCartForm(FlaskForm):
    quantity = IntegerField('Quantity', validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField('Add to Cart')

class CartUpdateForm(FlaskForm):
    submit = SubmitField('Update Cart')

@bp.route('/')
def home():
    return render_template('home.html')

@bp.route('/products')
def products():
    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = 8
    query = Product.query
    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))
    pagination = query.order_by(Product.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    csrf_token = generate_csrf()
    return render_template('products.html', products=pagination.items, pagination=pagination, search=search, csrf_token=csrf_token)

@bp.route('/product/<int:product_id>', methods=['GET', 'POST'])
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    form = AddToCartForm()
    if form.validate_on_submit():
        quantity = form.quantity.data
        if 'cart' not in session:
            session['cart'] = {}
        cart = session['cart']
        cart_item = cart.get(str(product_id), {'quantity': 0})
        cart_item['quantity'] += quantity
        cart[str(product_id)] = cart_item
        session['cart'] = cart
        # Redirect based on source
        if request.form.get('from_products') == '1':
            return redirect(url_for('main.products'))
        return redirect(url_for('main.cart'))
    return render_template('product_detail.html', product=product, form=form)

@bp.route('/cart', methods=['GET', 'POST'])
def cart():
    cart = session.get('cart', {})
    form = CartUpdateForm()
    if request.method == 'POST' and form.validate_on_submit():
        # Update quantities or remove items
        for key in list(cart.keys()):
            if f'remove_{key}' in request.form:
                cart.pop(key)
            else:
                qty = int(request.form.get(f'quantity_{key}', 1))
                product = Product.query.get(int(key))
                max_qty = product.stock if product else 1
                if qty > max_qty:
                    cart[key]['quantity'] = max_qty
                elif qty > 0:
                    cart[key]['quantity'] = qty
                else:
                    cart.pop(key)
        session['cart'] = cart
        if 'proceed_to_checkout' in request.form:
            return redirect(url_for('main.checkout'))
        return redirect(url_for('main.cart'))
    product_ids = [int(pid) for pid in cart.keys()]
    products = Product.query.filter(Product.id.in_(product_ids)).all() if product_ids else []
    cart_items = []
    total = 0
    for product in products:
        quantity = cart[str(product.id)]['quantity']
        subtotal = float(product.price) * quantity
        total += subtotal
        cart_items.append({'product': product, 'quantity': quantity, 'subtotal': subtotal})
    return render_template('cart.html', cart_items=cart_items, total=total, form=form)

@bp.route('/checkout', methods=['GET', 'POST'])
def checkout():
    cart = session.get('cart', {})
    if not cart:
        return redirect(url_for('main.cart'))
    product_ids = [int(pid) for pid in cart.keys()]
    products = Product.query.filter(Product.id.in_(product_ids)).all() if product_ids else []
    cart_items = []
    total = 0
    for product in products:
        quantity = cart[str(product.id)]['quantity']
        subtotal = float(product.price) * quantity
        total += subtotal
        cart_items.append({'product': product, 'quantity': quantity, 'subtotal': subtotal})
    form = CheckoutForm()
    if form.validate_on_submit():
        order = Order(
            name=form.name.data,
            email=form.email.data,
            address=form.address.data,
            phone=form.phone.data,
            total_price=total
        )
        db.session.add(order)
        db.session.commit()
        for item in cart_items:
            order_item = OrderItem(
                order_id=order.id,
                product_id=item['product'].id,
                quantity=item['quantity'],
                price=item['product'].price
            )
            db.session.add(order_item)
            # Reduce stock
            item['product'].stock -= item['quantity']
        db.session.commit()
        session.pop('cart', None)
        return redirect(url_for('main.order_confirmation', order_id=order.id))
    return render_template('checkout.html', form=form, cart_items=cart_items, total=total)

@bp.route('/order/<int:order_id>/confirmation')
def order_confirmation(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template('order_confirmation.html', order=order) 