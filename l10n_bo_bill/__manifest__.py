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
        'views/leyenda_factura_views.xml',
        'views/producto_servicio_views.xml',
        'views/unidades_medida_views.xml',
        'views/sucursal_views.xml',
        'views/punto_venta_views.xml',
        'views/cufd_views.xml',
        'views/cuis_views.xml',
        'views/evento_significativo_views.xml',
        'views/motivo_anulacion_views.xml',
        'views/pais_origen_views.xml',
        'views/tipos_factura_views.xml',
        'views/tipos_documento_identidad_views.xml',
        'views/tipos_documento_sector_views.xml',
        'views/tipos_emision_views.xml',
        'views/tipos_habitacion_views.xml',
        'views/tipos_punto_venta_views.xml',
        
        'wizards/anulacion_wizard_views.xml',
        'wizards/registrar_evento_contingencia_views.xml',
        'wizards/contingencia_wizard_view.xml',

        'views/res_partner_views.xml',
        'views/product_template_view.xml',
        'views/account_move_view.xml',
        #'views/payment_method_view.xml',
        'views/tipo_pago_view.xml',
        'views/res_company_view.xml',

        'data/cron_job.xml',
        'views/menu_views.xml',
    ],
    
    # 'assets': {
    #     'web.assets_backend': [
    #         'l10n_bo_bill/static/src/js/progress_modal.js',
    #         'l10n_bo_bill/static/src/xml/progress_modal_template.xml',
    #         'l10n_bo_bill/static/src/css/progress_modal.css',
    #     ],
    # },

 
    
    'installable': True,
    'application': True,
}
