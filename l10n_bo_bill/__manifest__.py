{
    'name': 'BO Billing',
    'version': '1.0',
    'category': 'Accounting',
    'summary': 'Módulo para gestionar la facturación electrónica en Bolivia.',
    'description': """
        Este módulo permite la gestión de direcciones API, leyendas de facturas, productos/servicios y unidades de medida.
    """,
    'depends': ['base', 'web' ,'contacts', 'stock', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'views/direccion_api_views.xml', 
        
        'views/cufd_views.xml', 
        'wizards/account_move_reversal_view_inherit.xml',
        'wizards/contingencia_inicio_wizard.xml',
        
        'views/res_partner_view.xml',
        'views/product_template_form_inherit.xml',
        'views/account_move_form_inherit.xml',
        
        'data/cufd_cron.xml',
        
    ],
    
 
    
    'installable': True,
    'application': True,
}
