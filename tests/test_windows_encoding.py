"""Windows locale-independent fixture loading and native-host JSON pipes."""
import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from core.app import App,main

class WindowsEncodingTest(unittest.TestCase):
 def test_fixture_reads_explicitly_use_utf8(self):
  original=Path.read_text
  def read(path,*args,**kwargs):
   self.assertEqual(kwargs.get('encoding'),'utf-8')
   return original(path,*args,**kwargs)
  with tempfile.TemporaryDirectory() as directory:
   with patch.object(Path,'read_text',read):app=App(directory,False)
   try:self.assertEqual(len(app.call('snapshot',{})['watch']),12)
   finally:app.store.db.close()

 def test_native_json_pipes_override_windows_locale(self):
  raw_in=io.BytesIO(b'{"method":"snapshot"}\n');raw_out=io.BytesIO()
  stdin=io.TextIOWrapper(raw_in,encoding='cp1252');stdout=io.TextIOWrapper(raw_out,encoding='cp1252')
  app=Mock();app.call.return_value={'name':'美利云'}
  with patch('core.app.App',return_value=app),patch('sys.stdin',stdin),patch('sys.stdout',stdout):main()
  stdout.flush();self.assertEqual(json.loads(raw_out.getvalue().decode('utf-8'))['data']['name'],'美利云')
  app.stop.set.assert_called_once()
