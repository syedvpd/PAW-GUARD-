import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.bulk import (
    BulkDeleteRequest,
    BulkDeleteResponse,
)
from pawguard.core.pagination import PageParams, page_params
from pawguard.core.responses import ApiResponse, PaginatedResponse
from pawguard.core.search import SortParams, sort_params
from pawguard.db.session import get_db
from pawguard.modules.auth.audit import get_audit_service
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.finance.models import (
    AccountType,
    ExpenseCategory,
    ExpenseStatus,
    TransactionStatus,
    TransactionType,
)
from pawguard.modules.finance.repository import FinanceRepository
from pawguard.modules.finance.schemas import (
    AccountBalanceResponse,
    BudgetCreate,
    BudgetItemCreate,
    BudgetResponse,
    ChartOfAccountsCreate,
    ChartOfAccountsResponse,
    ChartOfAccountsUpdate,
    DonationReconcileRequest,
    FinanceExpenseCreate,
    FinanceExpenseResponse,
    FinanceExpenseUpdate,
    FinancialTransactionCreate,
    FinancialTransactionResponse,
    FinancialTransactionUpdate,
    RecurringTransactionCreate,
    RecurringTransactionResponse,
    RefundRequest,
    RefundResponse,
    TaxReceipt80GRequest,
    TaxReceipt80GResponse,
)
from pawguard.modules.finance.service import FinanceService
from pawguard.services.audit_service import AuditService

router = APIRouter(prefix="/finance", tags=["finance"])


def get_finance_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> FinanceService:
    return FinanceService(FinanceRepository(db), audit_service=audit)


@router.post(
    "/accounts",
    response_model=ApiResponse[ChartOfAccountsResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("finance:create"))],
)
async def create_account(
    payload: ChartOfAccountsCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[ChartOfAccountsResponse]:
    ip = request.client.host if request.client else None
    account = await service.create_account(payload, actor_id=current_user.id, ip_address=ip)
    return ApiResponse(
        data=ChartOfAccountsResponse.model_validate(account),
        message="Account created.",
    )


@router.get(
    "/accounts",
    response_model=PaginatedResponse[ChartOfAccountsResponse],
    dependencies=[Depends(require_permission("finance:read"))],
)
async def list_accounts(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None),
    account_type: AccountType | None = Query(None),
    is_active: bool | None = Query(None),
    service: FinanceService = Depends(get_finance_service),
) -> PaginatedResponse[ChartOfAccountsResponse]:
    return await service.list_accounts_paginated(
        page, sort, search, account_type, is_active=is_active
    )


@router.get(
    "/accounts/{account_id}",
    response_model=ApiResponse[ChartOfAccountsResponse],
    dependencies=[Depends(require_permission("finance:read"))],
)
async def get_account(
    account_id: uuid.UUID,
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[ChartOfAccountsResponse]:
    account = await service.get_account(account_id)
    return ApiResponse(data=ChartOfAccountsResponse.model_validate(account))


@router.put(
    "/accounts/{account_id}",
    response_model=ApiResponse[ChartOfAccountsResponse],
    dependencies=[Depends(require_permission("finance:update"))],
)
async def update_account(
    account_id: uuid.UUID,
    payload: ChartOfAccountsUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[ChartOfAccountsResponse]:
    ip = request.client.host if request.client else None
    account = await service.update_account(
        account_id, payload, actor_id=current_user.id, ip_address=ip
    )
    return ApiResponse(
        data=ChartOfAccountsResponse.model_validate(account),
        message="Account updated.",
    )


@router.delete(
    "/accounts/{account_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("finance:update"))],
)
async def delete_account(
    account_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[None]:
    ip = request.client.host if request.client else None
    await service.soft_delete_account(account_id, actor_id=current_user.id, ip_address=ip)
    return ApiResponse(message="Account deleted.")


@router.post(
    "/transactions",
    response_model=ApiResponse[FinancialTransactionResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("finance:create"))],
)
async def create_transaction(
    payload: FinancialTransactionCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[FinancialTransactionResponse]:
    ip = request.client.host if request.client else None
    tx = await service.create_transaction(payload, actor_id=current_user.id, ip_address=ip)
    return ApiResponse(
        data=FinancialTransactionResponse.model_validate(tx),
        message="Transaction created.",
    )


@router.get(
    "/transactions",
    response_model=PaginatedResponse[FinancialTransactionResponse],
    dependencies=[Depends(require_permission("finance:read"))],
)
async def list_transactions(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None),
    transaction_type: TransactionType | None = Query(None),
    status: TransactionStatus | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    service: FinanceService = Depends(get_finance_service),
) -> PaginatedResponse[FinancialTransactionResponse]:
    return await service.list_transactions_paginated(
        page, sort, search, transaction_type, status, date_from, date_to
    )


@router.get(
    "/transactions/{tx_id}",
    response_model=ApiResponse[FinancialTransactionResponse],
    dependencies=[Depends(require_permission("finance:read"))],
)
async def get_transaction(
    tx_id: uuid.UUID,
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[FinancialTransactionResponse]:
    tx = await service.get_transaction(tx_id)
    return ApiResponse(data=FinancialTransactionResponse.model_validate(tx))


@router.patch(
    "/transactions/{tx_id}/status",
    response_model=ApiResponse[FinancialTransactionResponse],
    dependencies=[Depends(require_permission("finance:update"))],
)
async def update_transaction_status(
    tx_id: uuid.UUID,
    payload: FinancialTransactionUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[FinancialTransactionResponse]:
    ip = request.client.host if request.client else None
    tx = await service.update_transaction_status(
        tx_id,
        payload.status or TransactionStatus.POSTED,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=FinancialTransactionResponse.model_validate(tx),
        message="Transaction status updated.",
    )


@router.delete(
    "/transactions/{tx_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("finance:update"))],
)
async def delete_transaction(
    tx_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[None]:
    ip = request.client.host if request.client else None
    await service.soft_delete_transaction(tx_id, actor_id=current_user.id, ip_address=ip)
    return ApiResponse(message="Transaction deleted.")


@router.get(
    "/summary",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("finance:read"))],
)
async def get_finance_summary(
    period_start: date = Query(...),
    period_end: date = Query(...),
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_finance_summary(period_start, period_end)
    return ApiResponse(data=data)


@router.get(
    "/pnl",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("finance:read"))],
)
async def get_pnl(
    period_start: date = Query(...),
    period_end: date = Query(...),
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_pnl(period_start, period_end)
    return ApiResponse(data=data)


@router.get(
    "/account-balances",
    response_model=ApiResponse[list[AccountBalanceResponse]],
    dependencies=[Depends(require_permission("finance:read"))],
)
async def get_account_balances(
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[list[AccountBalanceResponse]]:
    data = await service.get_account_balances()
    return ApiResponse(data=data)


@router.post(
    "/reconcile/donations",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("finance:create"))],
)
async def reconcile_donations(
    request: Request,
    payload: DonationReconcileRequest | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[dict[str, Any]]:
    ip = request.client.host if request.client else None
    result = await service.reconcile_donations(
        donation_ids=payload.donation_ids if payload else None,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(data=result, message=f"Reconciled {result['reconciled']} donations.")


@router.get(
    "/reconcile/summary",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("finance:read"))],
)
async def get_reconciliation_summary(
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[dict[str, Any]]:
    data = await service.get_donation_reconciliation_summary()
    return ApiResponse(data=data)


@router.post(
    "/budgets",
    response_model=ApiResponse[BudgetResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("finance:create"))],
)
async def create_budget(
    payload: BudgetCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[BudgetResponse]:
    ip = request.client.host if request.client else None
    budget = await service.create_budget(payload, actor_id=current_user.id, ip_address=ip)
    return ApiResponse(
        data=BudgetResponse.model_validate(budget),
        message="Budget created.",
    )


@router.get(
    "/budgets",
    response_model=PaginatedResponse[BudgetResponse],
    dependencies=[Depends(require_permission("finance:read"))],
)
async def list_budgets(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None),
    fiscal_year: int | None = Query(None),
    is_active: bool | None = Query(None),
    service: FinanceService = Depends(get_finance_service),
) -> PaginatedResponse[BudgetResponse]:
    return await service.list_budgets_paginated(page, sort, search, fiscal_year, is_active)


@router.get(
    "/budgets/{budget_id}",
    response_model=ApiResponse[BudgetResponse],
    dependencies=[Depends(require_permission("finance:read"))],
)
async def get_budget(
    budget_id: uuid.UUID,
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[BudgetResponse]:
    budget = await service.get_budget(budget_id)
    return ApiResponse(data=BudgetResponse.model_validate(budget))


@router.post(
    "/budgets/{budget_id}/items",
    response_model=ApiResponse[BudgetResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("finance:update"))],
)
async def add_budget_item(
    budget_id: uuid.UUID,
    payload: BudgetItemCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[BudgetResponse]:
    ip = request.client.host if request.client else None
    budget = await service.add_budget_item(
        budget_id, payload, actor_id=current_user.id, ip_address=ip
    )
    return ApiResponse(
        data=BudgetResponse.model_validate(budget),
        message="Budget item added.",
    )


@router.delete(
    "/budgets/{budget_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("finance:update"))],
)
async def delete_budget(
    budget_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[None]:
    ip = request.client.host if request.client else None
    await service.soft_delete_budget(budget_id, actor_id=current_user.id, ip_address=ip)
    return ApiResponse(message="Budget deleted.")


@router.post(
    "/recurring",
    response_model=ApiResponse[RecurringTransactionResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("finance:create"))],
)
async def create_recurring(
    payload: RecurringTransactionCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[RecurringTransactionResponse]:
    ip = request.client.host if request.client else None
    rtx = await service.create_recurring(payload, actor_id=current_user.id, ip_address=ip)
    return ApiResponse(
        data=RecurringTransactionResponse.model_validate(rtx),
        message="Recurring transaction created.",
    )


@router.get(
    "/recurring",
    response_model=PaginatedResponse[RecurringTransactionResponse],
    dependencies=[Depends(require_permission("finance:read"))],
)
async def list_recurring(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None),
    is_active: bool | None = Query(None),
    service: FinanceService = Depends(get_finance_service),
) -> PaginatedResponse[RecurringTransactionResponse]:
    return await service.list_recurring_paginated(page, sort, search, is_active)


@router.delete(
    "/recurring/{rtx_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("finance:update"))],
)
async def delete_recurring(
    rtx_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[None]:
    ip = request.client.host if request.client else None
    await service.soft_delete_recurring(rtx_id, actor_id=current_user.id, ip_address=ip)
    return ApiResponse(message="Recurring transaction deleted.")


@router.post(
    "/accounts/bulk/delete",
    response_model=ApiResponse[BulkDeleteResponse],
    dependencies=[Depends(require_permission("finance:update"))],
)
async def bulk_delete_accounts(
    payload: BulkDeleteRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[BulkDeleteResponse]:
    ip = request.client.host if request.client else None
    deleted = await service.bulk_delete_accounts(
        payload.ids, actor_id=current_user.id, ip_address=ip
    )
    return ApiResponse(
        data=BulkDeleteResponse(
            message=f"{deleted} account(s) deleted.",
            deleted_count=deleted,
        ),
    )


@router.post(
    "/transactions/bulk/delete",
    response_model=ApiResponse[BulkDeleteResponse],
    dependencies=[Depends(require_permission("finance:update"))],
)
async def bulk_delete_transactions(
    payload: BulkDeleteRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[BulkDeleteResponse]:
    ip = request.client.host if request.client else None
    deleted = await service.bulk_delete_transactions(
        payload.ids, actor_id=current_user.id, ip_address=ip
    )
    return ApiResponse(
        data=BulkDeleteResponse(
            message=f"{deleted} transaction(s) deleted.",
            deleted_count=deleted,
        ),
    )


@router.post(
    "/expenses",
    response_model=ApiResponse[FinanceExpenseResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("finance:create"))],
)
async def create_expense(
    payload: FinanceExpenseCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[FinanceExpenseResponse]:
    ip = request.client.host if request.client else None
    expense = await service.create_expense(payload, actor_id=current_user.id, ip_address=ip)
    return ApiResponse(
        data=FinanceExpenseResponse.model_validate(expense),
        message="Expense created.",
    )


@router.get(
    "/expenses",
    response_model=PaginatedResponse[FinanceExpenseResponse],
    dependencies=[Depends(require_permission("finance:read"))],
)
async def list_expenses(
    page: PageParams = Depends(page_params),
    sort: SortParams = Depends(sort_params),
    search: str | None = Query(None),
    category: ExpenseCategory | None = Query(None),
    expense_status: ExpenseStatus | None = Query(None, alias="status"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    service: FinanceService = Depends(get_finance_service),
) -> PaginatedResponse[FinanceExpenseResponse]:
    return await service.list_expenses_paginated(
        page, sort, search, category, expense_status, date_from, date_to
    )


@router.get(
    "/expenses/{expense_id}",
    response_model=ApiResponse[FinanceExpenseResponse],
    dependencies=[Depends(require_permission("finance:read"))],
)
async def get_expense(
    expense_id: uuid.UUID,
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[FinanceExpenseResponse]:
    expense = await service.get_expense(expense_id)
    return ApiResponse(data=FinanceExpenseResponse.model_validate(expense))


@router.patch(
    "/expenses/{expense_id}",
    response_model=ApiResponse[FinanceExpenseResponse],
    dependencies=[Depends(require_permission("finance:update"))],
)
async def update_expense(
    expense_id: uuid.UUID,
    payload: FinanceExpenseUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[FinanceExpenseResponse]:
    ip = request.client.host if request.client else None
    expense = await service.update_expense(
        expense_id, payload, actor_id=current_user.id, ip_address=ip
    )
    return ApiResponse(
        data=FinanceExpenseResponse.model_validate(expense),
        message="Expense updated.",
    )


@router.post(
    "/expenses/{expense_id}/submit",
    response_model=ApiResponse[FinanceExpenseResponse],
    dependencies=[Depends(require_permission("finance:update"))],
)
async def submit_expense(
    expense_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[FinanceExpenseResponse]:
    ip = request.client.host if request.client else None
    expense = await service.submit_expense(expense_id, actor_id=current_user.id, ip_address=ip)
    return ApiResponse(
        data=FinanceExpenseResponse.model_validate(expense),
        message="Expense submitted for approval.",
    )


@router.post(
    "/expenses/{expense_id}/approve",
    response_model=ApiResponse[FinanceExpenseResponse],
    dependencies=[Depends(require_permission("finance:update"))],
)
async def approve_expense(
    expense_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[FinanceExpenseResponse]:
    ip = request.client.host if request.client else None
    expense = await service.approve_expense(expense_id, actor_id=current_user.id, ip_address=ip)
    return ApiResponse(
        data=FinanceExpenseResponse.model_validate(expense),
        message="Expense approved.",
    )


@router.post(
    "/expenses/{expense_id}/reject",
    response_model=ApiResponse[FinanceExpenseResponse],
    dependencies=[Depends(require_permission("finance:update"))],
)
async def reject_expense(
    expense_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FinanceService = Depends(get_finance_service),
    reason: str = Query(..., min_length=5),
) -> ApiResponse[FinanceExpenseResponse]:
    ip = request.client.host if request.client else None
    expense = await service.reject_expense(
        expense_id, reason, actor_id=current_user.id, ip_address=ip
    )
    return ApiResponse(
        data=FinanceExpenseResponse.model_validate(expense),
        message="Expense rejected.",
    )


@router.post(
    "/expenses/{expense_id}/pay",
    response_model=ApiResponse[FinanceExpenseResponse],
    dependencies=[Depends(require_permission("finance:update"))],
)
async def pay_expense(
    expense_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[FinanceExpenseResponse]:
    ip = request.client.host if request.client else None
    expense = await service.pay_expense(expense_id, actor_id=current_user.id, ip_address=ip)
    return ApiResponse(
        data=FinanceExpenseResponse.model_validate(expense),
        message="Expense marked as paid and posted to ledger.",
    )


@router.delete(
    "/expenses/{expense_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("finance:update"))],
)
async def delete_expense(
    expense_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[None]:
    ip = request.client.host if request.client else None
    await service.soft_delete_expense(expense_id, actor_id=current_user.id, ip_address=ip)
    return ApiResponse(message="Expense deleted.")


@router.post(
    "/refunds",
    response_model=ApiResponse[RefundResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("finance:create"))],
)
async def process_refund(
    payload: RefundRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[RefundResponse]:
    ip = request.client.host if request.client else None
    refund = await service.process_refund(
        donation_id=payload.donation_id,
        reason=payload.reason,
        refund_amount=payload.refund_amount,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=refund,
        message="Refund processed successfully.",
    )


@router.post(
    "/80g-certificate",
    response_model=ApiResponse[TaxReceipt80GResponse],
    dependencies=[Depends(require_permission("finance:read"))],
)
async def generate_80g_certificate(
    payload: TaxReceipt80GRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: FinanceService = Depends(get_finance_service),
) -> ApiResponse[TaxReceipt80GResponse]:
    cert = await service.generate_80g_certificate(
        donation_id=payload.donation_id,
        actor_id=current_user.id,
    )
    return ApiResponse(
        data=cert,
        message="80G certificate generated.",
    )


@router.get(
    "/reports/pdf",
    dependencies=[Depends(require_permission("finance:export"))],
)
async def generate_finance_report_pdf(
    period_start: date = Query(...),
    period_end: date = Query(...),
    service: FinanceService = Depends(get_finance_service),
) -> Response:
    import asyncio

    from pawguard.core.config import get_settings
    from pawguard.core.pdf_generation import generate_finance_report_pdf

    summary = await service.get_finance_summary(period_start, period_end)
    pnl = await service.get_pnl(period_start, period_end)
    settings = get_settings()

    pdf_bytes = await asyncio.to_thread(
        generate_finance_report_pdf,
        report_title="Financial Report",
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
        summary_data=summary,
        income_rows=pnl.get("income", []),
        expense_rows=pnl.get("expenses", []),
        org_name=settings.org_name,
        org_address=settings.org_address,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="finance_report_{period_start}_{period_end}.pdf"'
            )
        },
    )
