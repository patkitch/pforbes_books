# jobber_sync/graphql/queries.py

INVOICES_WINDOW = """
query InvoicesWindow(
  $first: Int!
  $after: String
  $filter: InvoiceFilterAttributes
  $sort: [InvoiceSortInput!]
) {
  invoices(first: $first, after: $after, filter: $filter, sort: $sort) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      id
      invoiceNumber
      invoiceStatus
      issuedDate
      dueDate
      receivedDate
      invoiceNet
      createdAt
      updatedAt

      amounts {
        subtotal
        taxAmount
        tipsTotal
        paymentsTotal
        invoiceBalance
        total
      }

      client {
        id
        name
      }
    }
  }
}
"""
