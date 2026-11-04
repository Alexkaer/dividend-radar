import unittest
from fundamentals import company_analysis,sector_summary,quarter_dates

def row(**changes):
    return dict(REPORT_DATE='2026-09-30',NOTICE_DATE='2026-10-30',INDUSTRY_NAME='白色家电',TOTAL_OPERATE_INCOME=100,PARENT_NETPROFIT=10,DEDUCT_PARENT_NETPROFIT=9,TOI_RATIO=8,PARENT_NETPROFIT_RATIO=15,DPN_RATIO=10,**changes)

class FinancialTests(unittest.TestCase):
    def test_strong_and_cash_warning(self):
        result=company_analysis(row(),cash={'NETCASH_OPERATE':-1})
        self.assertEqual(result['label'],'向好')
        self.assertTrue(any('现金流为负' in r for r in result['risks']))

    def test_loss_and_turnaround_override_growth(self):
        r=row();r['PARENT_NETPROFIT']=-2
        self.assertEqual(company_analysis(r)['label'],'亏损')
        self.assertEqual(company_analysis(row(),{'PARENT_NETPROFIT':-2})['label'],'扭亏')

    def test_missing_not_zero_and_financial_exemption(self):
        r=row();r['TOI_RATIO']=None
        self.assertEqual(company_analysis(r)['label'],'数据不足')
        r=row();r['INDUSTRY_NAME']='银行Ⅱ'
        result=company_analysis(r,cash={'NETCASH_OPERATE':-100})
        self.assertIsNone(result['cashProfitRatio'])
        self.assertFalse(any('现金流为负' in x for x in result['risks']))

    def test_peer_coverage_and_sample_size(self):
        self.assertEqual(sector_summary([row()]*5,10)['label'],'样本不足')
        self.assertEqual(sector_summary([row()]*2,2)['label'],'样本不足')
        self.assertEqual(sector_summary([row()]*5,5)['label'],'向好')

    def test_sector_profit_med_excludes_losses(self):
        r=row();r['PARENT_NETPROFIT']=-1;r['PARENT_NETPROFIT_RATIO']=1000
        result=sector_summary([row(),row(),row(),r],4)
        self.assertEqual(result['profitGrowthMedian'],15)
        self.assertEqual(result['profitableShare'],0.75)

    def test_quarter_boundary(self):
        self.assertEqual(quarter_dates('2026-11-04'),('2026-09-30','2026-06-30'))
        self.assertEqual(quarter_dates('2026-01-02'),('2025-12-31','2025-09-30'))

if __name__=='__main__':unittest.main()
