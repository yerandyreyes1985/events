# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, exceptions
from odoo.tools.translate import _, html_translate
from odoo.addons.http_routing.models.ir_http import slug
from odoo import SUPERUSER_ID
import uuid


class TrackTag(models.Model):
    _name = "event.track.tag"
    _inherit = 'event.track.tag'
    
    def split(self):
        """splits into single words"""
        
        all_tags = self.env['event.track.tag'].search([('name','like',';')])
        delete_list = []
        for i in range(0, len(all_tags)):
            name = str(all_tags[i].name)
            words = name.split(';')
            tags = []
            for kw in words:
                kw = kw.strip()
                kw = kw.rstrip()
                #kw = kw.lower()
                if kw:
                    otags = self.env['event.track.tag'].search([('name', '=', kw)])
                    if not otags:
                        tag = self.env['event.track.tag'].create({'name': kw})
                        tags.append(tag)
                    else:
                        tags += otags            
            
            for tag in tags:
                for track in all_tags[i].track_ids:
                    tag.track_ids = [(4, track.id)]
            
            if all_tags[i] not in tags:
                delete_list.append(all_tags[i])
        
        for it in delete_list:
            it.unlink()
                
    
class TrackStage(models.Model):
    _name = 'event.track.stage'
    _inherit = 'event.track.stage'

    def validate(self, track):
        review_workflow = self.env['ir.config_parameter'].sudo().get_param('website_event_track_uclv.review_workflow') == 'True'
        if review_workflow:
            if self.id == 2:
                if not track.reviewer_id or not track.reviewer2_id:
                    return False, _("You must assign reviewers to this track in order to set it in this state")
            if self.id == 3: #accepted
                if not track.partner_id:
                    return False, _("You must assign an speaker to this track in order to set it in this state")
                if not track.recommendation or not track.recommendation2:
                    return False, _("You must assign reviewers recomendations to this track in order to set it in this state")
                track.website_published = True
            if self.id == 4: #scheduled
                if not track.location_id or not track.date:
                    return False, _("You must assign location and date to this track in order to set it in this state")
                track.website_published = True
            if self.id in (1, 5, 6):             
                track.website_published = False
            return True, ''
        else:
            if self.id == 3: #accepted
                track.website_published = True
            if self.id == 4: #scheduled
                track.website_published = True
            if self.id in (1, 5, 6):
                track.website_published = False
            return True, ''

    def pre_validate(self, track, vals):
        if self.id == 1: #proposal
            if not vals.get('reviewer_id', track.reviewer_id) or not vals.get('reviewer2_id', track.reviewer2_id):
                return 2
            if vals.get('reviewer_id', track.reviewer_id) and vals.get('reviewer2_id', track.reviewer2_id):
                return 0
        if self.id == 2: #review
            if not vals.get('partner_id', track.partner_id) or not vals.get('recommendation', track.recommendation) or not vals.get('recommendation2',track.recommendation2):
                return 2
            if vals.get('partner_id', track.partner_id) and vals.get('recommendation', track.recommendation) and vals.get('recommendation2', track.recommendation2):
                return 0
        if self.id == 3: #accepted
            if not vals.get('location_id', track.location_id) or not vals.get('date', track.date) or not vals.get('recommendation2',track.recommendation2):
                return 2
            if vals.get('location_id', track.location_id) and vals.get('date', track.recommendation) and vals.get('recommendation2', track.date):
                return 0
        
        return 1
        

class TrackType(models.Model):
    _name = 'event.track.type'
    name = fields.Char('Name', required=True, translate=True)
    description = fields.Char('Description', translate=True)


class TrackLocation(models.Model):
    _name = "event.track.location"
    _inherit = "event.track.location"    

    name = fields.Char('Room')
    partner_id = fields.Many2one('res.partner')
    
    _sql_constraints = [('name_uniq_partner', 'unique(name, partner_id)', _('Name must be unique by partner!'))]


class TrackAuthor(models.Model):
    _name = 'event.track.author'

    event_track_id = fields.Many2one('event.track', string="Track", required=True, ondelete='cascade')
    res_partner_id = fields.Many2one('res.partner', string="Partner", required=True, ondelete='cascade')
    sequence = fields.Integer(string="Sequence", default=1)

    _sql_constraints = [('track_uniq_partner', 'unique(event_track_id, res_partner_id)', _('Authors can only appear once per paper'))]


class Track(models.Model):
    _name = "event.track"    
    _inherit = ['event.track', 'portal.mixin', 'mail.thread', 'mail.activity.mixin', 'website.seo.metadata', 'website.published.mixin']
    
    def _get_reviewed(self):
        self.reviewed = False
        if self.reviewer_id.id == self.env.user.id:
            if self.recommendation:
                self.reviewed = True
        if self.reviewer2_id.id == self.env.user.id:
            if self.recommendation2:
                self.reviewed = True

    
    def _get_multiple(self):
        for item in self:
            if self.search_count([('name', '=', item.name),('event_id', '=', item.event_id.id)]) > 1:
                item.multiple = True
            else:
                item.multiple = False

    @api.depends('description')
    def compute_description_lang(self):
        from langdetect import detect
        from odoo.tools import html2plaintext
        for item in self:
            try:
                item.description_lang = detect(html2plaintext(item.description))
            except:
                item.description_lang = ''

    address_id = fields.Many2one('res.partner', "Address", related="event_id.address_id", readonly=True)
    multiple = fields.Boolean("Multiple", compute="_get_multiple", store=True)
    track_type_id = fields.Many2one('event.track.type', "Track Type")
    publish_complete = fields.Boolean(string="Can be Published", default=True)
    reviewed = fields.Boolean("Reviewed", compute="_get_reviewed", store=False)
    user_id = fields.Many2one('res.users', related="event_id.user_id", string='Coordinator', readonly=True)
    reviewer_id = fields.Many2one('res.users', 'First Reviewer', default=False, domain=[("reviewer", '=', True)])
    reviewer2_id = fields.Many2one('res.users', 'Second Reviewer', default=False, domain=[("reviewer", '=', True)])
    attachment_ids = fields.One2many('ir.attachment', 'res_id', domain=[('res_model', '=', 'event.track')], string='Attachments')
    author_ids = fields.One2many('event.track.author', 'event_track_id', string='Authors')
    partner_id = fields.Many2one('res.partner', 'Speaker', required=True, domain=[('email', '!=', None)])
    partner_name = fields.Char('Speaker Name', related='partner_id.full_name')
    partner_email = fields.Char('Speaker Email', readonly=True, related='partner_id.email')
    email = fields.Char('Speaker Email', readonly=True, related='partner_id.email')
    partner_phone = fields.Char('Speaker Phone', readonly=True, related='partner_id.phone')
    partner_country = fields.Many2one('res.country','Speaker Country', readonly=True, related='partner_id.country_id')
    partner_institution = fields.Char('Speaker Institution', readonly=True, related='partner_id.institution')
    authenticity_url = fields.Char("Authenticity URL", compute="get_urls")
    authenticity_token = fields.Char("Authenticity Token")
    description =  fields.Html("Description", sanitize_tags=True)
    description_lang = fields.Char(compute="compute_description_lang", store=True)
    
    tag_ids = fields.Many2many('event.track.tag', string='Keywords')
    kanban_state = fields.Selection([
        ('normal', 'Grey'),
        ('done', 'Green'),
        ('blocked', 'Red')], string='Kanban State',
        copy=False, default='blocked', required=True,
        help="A track's kanban state indicates special situations affecting it:\n"
             " * Grey is the default situation\n"
             " * Red indicates something is preventing the progress of this track\n"
             " * Green indicates the track is ready to be pulled to the next stage")
    language_id = fields.Many2one("res.lang", "Language")
    duration = fields.Float('Duration', default=0.25)
    image = fields.Binary('Image', related='partner_id.image_512', store=True, attachment=True)

    #Revision Stuffs
    coordinator_notes = fields.Text('Notes for the Coordinator')
    author_notes = fields.Text('Notes for the Author')
    recommendation = fields.Selection([('acceptwc', "Accepted With Changes"), ('acceptednc', "Accepted Without Changes"),  ('rejected', "Rejected")], 'Recommendation')

    coordinator_notes2 = fields.Text('Notes for the Coordinator')
    author_notes2 = fields.Text('Notes for the Author')
    recommendation2 = fields.Selection(
        [('acceptwc', "Accepted With Changes"), ('acceptednc', "Accepted Without Changes"), ('rejected', "Rejected")],
        'Recommendation')

    def build_uuids(self):
        regs = self.search([('authenticity_token', '=', False)])
        for reg in regs:
            reg.write({'authenticity_token': uuid.uuid1()})

    def get_urls(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for item in self:
            item.authenticity_url = base_url+'/events/auth/'+str(item.authenticity_token)

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            #self.partner_name = self.partner_id.name
            #self.partner_email = self.partner_id.email
            #self.partner_phone = self.partner_id.phone
            self.partner_biography = self.partner_id.website_description

    @api.model
    def create(self, vals):
        location_id = vals.get('location_id', False)
        if location_id:
            location = self.env['event.track.location'].browse(location_id)
            event = self.env['event.event'].browse(vals.get('event_id'))
            if location:
                if location.partner_id != event.address_id:
                    raise exceptions.Warning(_('Room is not valid for this event'))
        
        if not vals.get('authenticity_token', False):
            vals.update({'authenticity_token': uuid.uuid1()})
        
        return super(Track, self).create(vals)

        
    def write(self, vals):
        group = self.env.ref('event_uclv.group_event_multimanager')
        if self.env.user not in group.sudo().users:
            if  self.user_id.id != self.env.user.id and \
                self.reviewer_id.id != self.env.user.id and \
                self.reviewer2_id.id != self.env.user.id and \
                self.partner_id.user_id.id != self.env.user.id:
                raise exceptions.Warning(_("You are not authorized to change this track"))

        if 'stage_id' in vals and 'kanban_state' not in vals:
            vals['kanban_state'] = 'normal'
        
        #if not vals.get('partner_email', self.partner_email):
        #    raise exceptions.Warning(_('Speakers must have an email!'))
        
        location_id = vals.get('location_id', self.location_id.id)
        if location_id:
            location = self.env['event.track.location'].browse(location_id)
            event = self.env['event.event'].browse(vals.get('event_id', self.event_id.id))
            if location:
                if location.partner_id != event.address_id:
                    raise exceptions.Warning(_('Room is not valid for this event'))
        

        #revision
        stage_id = vals.get('stage_id', self.stage_id.id)
        if stage_id:
            stage = self.env['event.track.stage'].browse(stage_id)
            res = stage.pre_validate(self, vals)
            if res == 2:
                vals.update({'kanban_state': 'blocked'})
            if res == 0:
                vals.update({'kanban_state': 'done'})
        
        stage_id = vals.get('stage_id', False)
        if stage_id:
            stage = self.env['event.track.stage'].browse(stage_id)
            res, err = stage.validate(self)
            if not res:
                raise exceptions.Warning(err)

        res = super(Track, self).write(vals)
        
        url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        user_name = self.env.user.name
        company_name = self.env.ref('base.main_company').name
        if vals.get('reviewer_id'):

            self.message_subscribe([vals['reviewer_id']])
            mail = self.env['mail.mail'].create(
                {
                    'email_from': 'convencionuclv@uclv.cu', 
                    'reply_to': 'convencionuclv@uclv.cu', 
                    'email_to': self.reviewer_id.email, 
                    'subject': _("Reviewer of track"), 
                    'notification': True,
                    'auto_delete': True,
                    'body_html': _('<div><p>Dear %s:</p><p>We are glad to inform you that you have been selected to review the proposal %s for the event %s.</p><p>You will find more details here:<div style="margin-top: 16px;"><a href="%s/my/track/%s" style="padding: 8px 12px; font-size: 12px; color: #FFFFFF; text-decoration: none !important; font-weight: 400; background-color: #003399; border: 0px solid #003399; border-radius:3px">View Track</a></div></p><p>Sincerely, %s</p><br/><p><a href="%s">%s</a></p></div>') % (self.reviewer_id.name, self.name, self.event_id.name, url, str(self.id), user_name, url, company_name)
                })
            mail.send()
        if vals.get('reviewer2_id'):
            self.message_subscribe([vals['reviewer2_id']])
            mail = self.env['mail.mail'].create(
                {
                    'email_from': 'convencionuclv@uclv.cu', 
                    'reply_to': 'convencionuclv@uclv.cu', 
                    'email_to': self.reviewer2_id.email, 
                    'subject': _("Reviewer of track"), 
                    'notification': True,
                    'auto_delete': True,
                    'body_html': _('<div><p>Dear %s:</p><p>We are glad to inform you that you have been selected to review the proposal %s for the event %s.</p><p>You will find more details here:<div style="margin-top: 16px;"><a href="%s/my/track/%s" style="padding: 8px 12px; font-size: 12px; color: #FFFFFF; text-decoration: none !important; font-weight: 400; background-color: #003399; border: 0px solid #003399; border-radius:3px">View Track</a></div></p><p>Sincerely, %s</p><br/><p><a href="%s">%s</a></p></div>') % (self.reviewer2_id.name, self.name, self.event_id.name, url, str(self.id), user_name, url, company_name)
                })
            mail.send()
        if vals.get('partner_id'):
            self.message_subscribe([vals['partner_id']])
        return res

    
    """def _track_template(self, tracking):
        res = super(Track, self)._track_template(tracking)
        track = self[0]
        changes, tracking_value_ids = tracking[track.id]
        #if 'reviewer_id' in changes and track.reviewer_id.email:
        #    res['reviewer_id'] = (self.env.ref("website_event_track.reviewer_mail_template"), {'composition_mode': 'mass_mail', 'email_to': 'yed@yed.com'})
        if 'stage_id' in changes and track.stage_id.mail_template_id:
            res['stage_id'] = (track.stage_id.mail_template_id, {'composition_mode': 'mass_mail'})
        return res"""

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        args = args or []
        recs = self.browse()
        group1 = self.env.ref('event_uclv.group_event_multimanager')
        if self.env.user not in group1.sudo().users:
            args += [("user_id", "=", self.env.user.id)]
        if name:
            recs = self.search([('name', 'ilike', name)] + args, limit=limit)
        if not recs:
            recs = self.search([('name', operator, name)] + args, limit=limit)
        return recs.name_get() 

    
    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        new_domain = []
        group = self.env.ref('event_uclv.group_event_multimanager')
        if self.env.user not in group.sudo().users:
            #new_domain.append(("user_id", "=", self.env.user.id))
            new_domain +=[("user_id", "=", self.env.user.id)]
        for arg in domain:
            new_domain.append(arg)
        return super(Track, self).read_group(new_domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
   
    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        new_args = []
        group = self.env.ref('event_uclv.group_event_multimanager')
        if self.env.user not in group.sudo().users:
            #new_args.append(("user_id", "=", self.env.user.id))
            new_args += [("user_id", "=", self.env.user.id)]
        for arg in args:
            new_args.append(arg)

        return super(Track, self).search(new_args, offset=offset, limit=limit, order=order, count=count)


    