# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from datetime import datetime

from flask import url_for
from flask.ext.restful import fields

from udata.api import api, ModelAPI, ModelListAPI, API, marshal, pager
from udata.auth import current_user
from udata.forms import OrganizationForm, MembershipRequestForm, MembershipRefuseForm
from udata.models import Organization, MembershipRequest, Member, FollowOrg

from udata.core.followers.api import FollowAPI

from .search import OrganizationSearch

ns = api.namespace('organizations', 'Organization related operations')

org_fields = api.model('Organization', {
    'id': fields.String,
    'name': fields.String,
    'slug': fields.String,
    'description': fields.String,
    'created_at': fields.ISODateTime,
    'last_modified': fields.ISODateTime,
    'deleted': fields.ISODateTime,
    'metrics': fields.Raw,
    'uri': fields.UrlFor('api.organization', lambda o: {'org': o}),
})

org_page_fields = api.model('OrganizationPage', pager(org_fields))

request_fields = api.model('MembershripRequest', {
    'status': fields.String,
    'comment': fields.String,
})

member_fields = api.model('Member', {
    'user': fields.String,
    'role': fields.String,
})

common_doc = {
    'params': {'org': 'The organization ID or slug'}
}


@api.model('OrganizationReference')
class OrganizationField(fields.Raw):
    def format(self, organization):
        return {
            'id': str(organization.id),
            'uri': url_for('api.organization', org=organization, _external=True),
            'page': url_for('organizations.show', org=organization, _external=True),
        }


@ns.route('/', endpoint='organizations')
@api.doc(get={'model': org_page_fields}, post={'model': org_fields})
class OrganizationListAPI(ModelListAPI):
    model = Organization
    fields = org_fields
    form = OrganizationForm
    search_adapter = OrganizationSearch


@ns.route('/<org:org>/', endpoint='organization', doc=common_doc)
@api.doc(model=org_fields)
class OrganizationAPI(ModelAPI):
    model = Organization
    fields = org_fields
    form = OrganizationForm


@ns.route('/<org:org>/membership/', endpoint='request_membership', doc=common_doc)
class MembershipRequestAPI(API):
    @api.secure
    @api.doc(model=request_fields)
    def post(self, org):
        '''Apply for membership to a given organization.'''
        membership_request = org.pending_request(current_user._get_current_object())
        code = 200 if membership_request else 201

        form = api.validate(MembershipRequestForm, membership_request)

        if not membership_request:
            membership_request = MembershipRequest()
            org.requests.append(membership_request)

        form.populate_obj(membership_request)
        org.save()

        return marshal(membership_request, request_fields), code


class MembershipAPI(API):
    def get_or_404(self, org, id):
        for membership_request in org.requests:
            if membership_request.id == id:
                return membership_request
        api.abort(404, 'Unknown membership request id')


@ns.route('/<org:org>/membership/<uuid:id>/accept/', endpoint='accept_membership', doc=common_doc)
class MembershipAcceptAPI(MembershipAPI):
    @api.secure
    @api.doc(model=member_fields)
    def post(self, org, id):
        '''Accept user membership to a given organization.'''
        membership_request = self.get_or_404(org, id)

        membership_request.status = 'accepted'
        membership_request.handled_by = current_user._get_current_object()
        membership_request.handled_on = datetime.now()
        member = Member(user=membership_request.user, role='editor')

        org.members.append(member)
        org.save()

        return marshal(member, member_fields), 200


@ns.route('/<org:org>/membership/<uuid:id>/refuse/', endpoint='refuse_membership', doc=common_doc)
class MembershipRefuseAPI(MembershipAPI):
    @api.secure
    def post(self, org, id):
        '''Refuse user membership to a given organization.'''
        membership_request = self.get_or_404(org, id)
        form = api.validate(MembershipRefuseForm)

        membership_request.status = 'refused'
        membership_request.handled_by = current_user._get_current_object()
        membership_request.handled_on = datetime.now()
        membership_request.refusal_comment = form.comment.data

        org.save()

        return {}, 200


@ns.route('/<id>/follow/', endpoint='follow_organization')
class FollowOrgAPI(FollowAPI):
    model = FollowOrg
