from odoo import models, fields, api
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)


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
    contingencia = fields.Boolean(string="Contingencia", default=False)
    evento_id = fields.Integer(string="ID del Evento de Contingencia")



