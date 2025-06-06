from odoo import models, fields

class DireccionApi(models.Model):
    _name = 'l10n_bo_bill.direccion_api'
    _description = 'Direccion API'

    name = fields.Char(string='Nombre', required=True)
    url = fields.Char(string='URL', required=True)
    tipo = fields.Selection(
        [
            ('computarizada', 'Computarizada'),
            ('electronica', 'Electrónica')
        ], 
        string='Tipo',
        required=True
    )
    
    activo = fields.Boolean(string='Activo', default=True)
    